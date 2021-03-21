# -*- coding: future_annotations -*-
import ast
from contextlib import contextmanager
import logging
from typing import TYPE_CHECKING

from nbsafety.analysis.symbol_edges import get_symbol_edges, get_symbol_rvals
from nbsafety.analysis.utils import stmt_contains_lval
from nbsafety.data_model.data_symbol import DataSymbol
from nbsafety.data_model.scope import NamespaceScope, Scope
from nbsafety.singletons import nbs, tracer
from nbsafety.tracing.mutation_event import MutationEvent

if TYPE_CHECKING:
    from types import FrameType
    from typing import Any, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class TraceStatement(object):
    def __init__(self, frame: FrameType, stmt_node: ast.stmt, scope: Scope):
        self.frame = frame
        self.stmt_node = stmt_node
        self.scope = scope
        self.class_scope: Optional[NamespaceScope] = None
        self.call_point_deps: List[Set[DataSymbol]] = []
        self.lambda_call_point_deps_done_once = False
        self.call_seen = False

    @property
    def lineno(self):
        return self.stmt_node.lineno

    @contextmanager
    def replace_active_scope(self, new_active_scope):
        old_scope = self.scope
        self.scope = new_active_scope
        yield
        self.scope = old_scope

    @property
    def finished(self):
        return self.stmt_id in tracer().seen_stmts

    @property
    def stmt_id(self):
        return id(self.stmt_node)

    def _contains_lval(self):
        return stmt_contains_lval(self.stmt_node)

    def compute_rval_dependencies(self, rval_symbol_refs=None):
        if rval_symbol_refs is None:
            symbol_edges, _, _ = get_symbol_edges(self.stmt_node)
            if len(symbol_edges) == 0:
                rval_symbol_refs = set()
            else:
                rval_symbol_refs = set.union(*symbol_edges.values()) - {None}
        return tracer().resolve_symbols(rval_symbol_refs, scope=self.scope).union(*self.call_point_deps)

    def get_post_call_scope(self):
        old_scope = tracer().cur_frame_original_scope
        if isinstance(self.stmt_node, ast.ClassDef):
            # classes need a new scope before the ClassDef has finished executing,
            # so we make it immediately
            return self.scope.make_child_scope(self.stmt_node.name, obj_id=-1)

        if not isinstance(self.stmt_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # TODO: probably the right thing is to check is whether a lambda appears somewhere inside the ast node
            # if not isinstance(self.ast_node, ast.Lambda):
            #     raise TypeError('unexpected type for ast node %s' % self.ast_node)
            return old_scope
        func_name = self.stmt_node.name
        func_cell = nbs().statement_to_func_cell.get(id(self.stmt_node), None)
        if func_cell is None:
            # TODO: brittle; assumes any user-defined and traceable function will always be present; is this safe?
            return old_scope
        if not func_cell.is_function:
            if nbs().is_develop:
                raise TypeError('got non-function symbol %s for name %s' % (func_cell.full_path, func_name))
            else:
                # TODO: log an error to a file
                return old_scope
        if not self.finished:
            func_cell.create_symbols_for_call_args()
        return func_cell.call_scope

    def _resolve_scope_and_name_for_target(
        self, target: Union[str, ast.AST, int]
    ) -> Tuple[Scope, Union[str, int], Any, bool]:
        if isinstance(target, (ast.Name, str)):
            target = target.id if isinstance(target, ast.Name) else target
            obj = self.frame.f_locals[target]
            return tracer().cur_frame_original_scope, target, obj, False
        else:
            target = id(target) if isinstance(target, ast.AST) else target
            (
                scope, obj, attr_or_sub, is_subscript
            ) = tracer().node_id_to_saved_store_data[target]
            attr_or_sub_obj = nbs().retrieve_namespace_attr_or_sub(obj, attr_or_sub, is_subscript)
            scope_to_use = scope.get_earliest_ancestor_containing(id(attr_or_sub_obj), is_subscript)
            if scope_to_use is None:
                # Nobody before `scope` has it, so we'll insert it at this level
                scope_to_use = scope
            return scope_to_use, attr_or_sub, attr_or_sub_obj, is_subscript

    def _handle_assign_target_for_deps(
        self,
        target: ast.AST,
        deps: Set[DataSymbol],
        maybe_fixup_literal_namespace=False,
        literal_references: Optional[Set[DataSymbol]] = None
    ):
        overwrite = True
        scope, name, obj, is_subscript = self._resolve_scope_and_name_for_target(target)
        if literal_references is not None:
            prev_sym = scope.lookup_data_symbol_by_name_this_indentation(name)
            if prev_sym is not None and prev_sym in literal_references:
                overwrite = False
        scope.upsert_data_symbol_for_name(
            # TODO: handle this at finer granularity
            name, obj, deps.union(*self.call_point_deps), self.stmt_node, is_subscript, overwrite=overwrite
        )
        if maybe_fixup_literal_namespace:
            namespace_for_upsert = nbs().namespaces.get(id(obj), None)
            if namespace_for_upsert is not None and namespace_for_upsert.scope_name == NamespaceScope.ANONYMOUS:
                namespace_for_upsert.scope_name = str(name)
                namespace_for_upsert.parent_scope = scope

    def _handle_assign_target_tuple_unpack_from_deps(self, target: Union[ast.List, ast.Tuple], deps: Set[DataSymbol]):
        for inner_target in target.elts:
            if isinstance(inner_target, (ast.List, ast.Tuple)):
                self._handle_assign_target_tuple_unpack_from_deps(inner_target, deps)
            else:
                self._handle_assign_target_for_deps(inner_target, deps)

    def _handle_assign_target_tuple_unpack_from_namespace(
        self, target: Union[ast.List, ast.Tuple], value: Optional[ast.AST], rhs_namespace: NamespaceScope
    ):
        if isinstance(value, (ast.List, ast.Tuple)) and len(value.elts) == len(target.elts):
            value_elts = value.elts
        else:
            value_elts = [None] * len(target.elts)
        for (i, inner_target), inner_value in zip(enumerate(target.elts), value_elts):
            if isinstance(inner_target, ast.Starred):
                break
            inner_dep = rhs_namespace.lookup_data_symbol_by_name_this_indentation(i, is_subscript=True)
            if inner_dep is None:
                inner_deps = set()
            else:
                inner_deps = {inner_dep}
            if isinstance(inner_target, (ast.List, ast.Tuple)):
                inner_namespace = nbs().namespaces.get(inner_dep.obj_id, None)
                if inner_namespace is None:
                    self._handle_assign_target_tuple_unpack_from_deps(inner_target, inner_deps)
                else:
                    self._handle_assign_target_tuple_unpack_from_namespace(inner_target, inner_value, inner_namespace)
            else:
                if inner_value is None:
                    literal_references = None
                else:
                    literal_references = tracer().resolve_symbols(get_symbol_rvals(inner_value))
                self._handle_assign_target_for_deps(
                    inner_target, inner_deps,
                    maybe_fixup_literal_namespace=True,
                    literal_references=literal_references,
                )

    def _handle_assign_target(self, target: ast.AST, value: ast.AST):
        if isinstance(target, (ast.List, ast.Tuple)):
            rhs_namespace = tracer().node_id_to_loaded_literal_scope.get(id(value), None)
            if rhs_namespace is None:
                rval_dsyms = tracer().resolve_symbols(get_symbol_rvals(value), scope=self.scope)
                if len(rval_dsyms) == 1:
                    rhs_namespace = nbs().namespaces.get(next(iter(rval_dsyms)).obj_id, None)
            if rhs_namespace is None:
                self._handle_assign_target_tuple_unpack_from_deps(target, tracer().resolve_symbols(get_symbol_rvals(value), scope=self.scope))
            else:
                self._handle_assign_target_tuple_unpack_from_namespace(target, value, rhs_namespace)
        else:
            rval_deps = tracer().resolve_symbols(get_symbol_rvals(value), scope=self.scope)
            literal_references = None
            if isinstance(value, (ast.Dict, ast.List, ast.Tuple)):
                literal_references = rval_deps
                if isinstance(value, ast.Dict):
                    rval_deps = tracer().resolve_symbols(
                        set.union(set(), *[get_symbol_rvals(k) for k in value.keys if k is not None]), scope=self.scope
                    )
                else:
                    rval_deps = set()
            self._handle_assign_target_for_deps(
                target, rval_deps, maybe_fixup_literal_namespace=True, literal_references=literal_references
            )

    def _handle_assign(self, node: ast.Assign):
        for target in node.targets:
            self._handle_assign_target(target, node.value)

    def _handle_literal_namespace(
        self, lval_name: Union[str, int], node_id: int, stored_attrsub_scope, stored_attrsub_name
    ):
        scope = tracer().node_id_to_loaded_literal_scope.get(node_id, None)
        if scope is None:
            return

        if isinstance(lval_name, str):
            scope.scope_name = lval_name
        elif isinstance(lval_name, int) and stored_attrsub_name is not None:
            scope.scope_name = stored_attrsub_name
            if stored_attrsub_scope is not None:
                scope.parent_scope = stored_attrsub_scope

    def _make_lval_data_symbols(self):
        if isinstance(self.stmt_node, ast.Assign):
            self._handle_assign(self.stmt_node)
        else:
            self._make_lval_data_symbols_old()

    def _handle_tuple_unpack(self, lval_ref: ast.AST, rval_refs: Set[Union[str, int]]):
        pass

    def _make_lval_data_symbols_old(self):
        symbol_edges, lval_name_to_literal_node_id, should_overwrite = get_symbol_edges(self.stmt_node)
        is_function_def = isinstance(self.stmt_node, (ast.FunctionDef, ast.AsyncFunctionDef))
        is_class_def = isinstance(self.stmt_node, ast.ClassDef)
        is_import = isinstance(self.stmt_node, (ast.Import, ast.ImportFrom))
        if is_function_def or is_class_def:
            assert len(symbol_edges) == 1
            # assert not lval_symbol_refs.issubset(rval_symbol_refs)

        for lval_name, rval_names in symbol_edges.items():
            rval_deps = self.compute_rval_dependencies(rval_symbol_refs=rval_names)
            # print('create edges from', rval_deps, 'to', lval_name)
            if is_class_def:
                assert self.class_scope is not None
                class_ref = self.frame.f_locals[self.stmt_node.name]
                class_obj_id = id(class_ref)
                self.class_scope.obj_id = class_obj_id
                nbs().namespaces[class_obj_id] = self.class_scope
            # if is_function_def:
            #     print('create function', name, 'in scope', self.scope)
            try:
                scope, name, obj, is_subscript = self._resolve_scope_and_name_for_target(lval_name)
                stored_attrsub_scope, stored_attrsub_name = None, None
                if isinstance(lval_name, int):
                    stored_attrsub_scope, stored_attrsub_name = scope, name
                scope.upsert_data_symbol_for_name(
                    name, obj, rval_deps, self.stmt_node, is_subscript,
                    overwrite=should_overwrite, is_function_def=is_function_def, is_import=is_import,
                    class_scope=self.class_scope, propagate=not isinstance(self.stmt_node, ast.For)
                )
                if lval_name in lval_name_to_literal_node_id:
                    self._handle_literal_namespace(
                        lval_name, lval_name_to_literal_node_id[lval_name], stored_attrsub_scope, stored_attrsub_name
                    )
            except KeyError:
                logger.warning('keyerror for %s', lval_name)
            except Exception as e:
                logger.warning('exception while handling store: %s', e)
                pass

    def handle_dependencies(self):
        if not nbs().dependency_tracking_enabled:
            return
        for mutated_obj_id, mutation_event, mutation_arg_dsyms in tracer().mutations:
            if mutation_event == MutationEvent.arg_mutate:
                for mutated_sym in mutation_arg_dsyms:
                    # TODO: happens when module mutates args
                    #  should we add module as a dep in this case?
                    mutated_sym.update_deps(set(), overwrite=False, mutated=True)
                continue

            # NOTE: this next block is necessary to ensure that we add the argument as a namespace child
            # of the mutated symbol. This helps to avoid propagating through to dependency children that are
            # themselves namespace children.
            if mutation_event == MutationEvent.list_append and len(mutation_arg_dsyms) == 1:
                namespace_scope = nbs().namespaces.get(mutated_obj_id, None)
                mutated_obj_aliases = nbs().aliases.get(mutated_obj_id, None)
                if mutated_obj_aliases is not None:
                    mutated_sym = next(iter(mutated_obj_aliases))
                    mutated_obj = mutated_sym._get_obj()
                    mutation_arg_sym = next(iter(mutation_arg_dsyms))
                    mutation_arg_obj = mutation_arg_sym._get_obj()
                    # TODO: replace int check w/ more general "immutable" check
                    if mutated_sym is not None and mutation_arg_obj is not None and not isinstance(mutation_arg_obj, int):
                        if namespace_scope is None:
                            namespace_scope = NamespaceScope(
                                mutated_obj,
                                mutated_sym.name,
                                parent_scope=mutated_sym.containing_scope
                            )
                        namespace_scope.upsert_data_symbol_for_name(
                            len(mutated_obj) - 1, mutation_arg_obj, set(), self.stmt_node,
                            is_subscript=True, overwrite=False, propagate=False
                        )
            # TODO: add mechanism for skipping namespace children in case of list append
            for mutated_sym in nbs().aliases[mutated_obj_id]:
                mutated_sym.update_deps(mutation_arg_dsyms, overwrite=False, mutated=True)
        if self._contains_lval():
            self._make_lval_data_symbols()
        else:
            if len(tracer().node_id_to_saved_store_data) > 0 and nbs().is_develop:
                logger.warning('saw unexpected state in saved_store_data: %s',
                               tracer().node_id_to_saved_store_data)

    def finished_execution_hook(self):
        if self.finished:
            return
        # print('finishing stmt', self.stmt_node)
        tracer().seen_stmts.add(self.stmt_id)
        self.handle_dependencies()
        tracer().after_stmt_reset_hook()
        nbs()._namespace_gc()
        # self.safety._gc()
