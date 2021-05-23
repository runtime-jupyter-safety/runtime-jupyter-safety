/*
 *  Copyright 2017 TWO SIGMA OPEN SOURCE, LLC
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *         http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */

// smacke: this was originally copied. license + copyright preserved as originally stated.
// ref: https://github.com/twosigma/beakerx/

var LabPageObject = function () {

  this.kernelIdleIcon = $('div.jp-Toolbar-kernelStatus svg[data-icon="ui-components:circle-empty"]');

  this.runNotebookByUrl = function(url, shortName){
    console.log('jupyter lab application');
    browser.url('http://127.0.0.1:9999/lab');
    browser.waitUntil(function(){
      return browser.$$('div.p-Widget.jp-BreadCrumbs.jp-FileBrowser-crumbs').length > 0;
    });
    browser.waitUntil(function(){
      return browser.$$('span.jp-DirListing-itemIcon').length > 0;
    });
    browser.$('span.jp-BreadCrumbs-home').click();
    browser.pause(1500);
    var dirs = (shortName != null)? shortName.split('/') : url.split('/');
    console.log(dirs);
    var i = 0;
    while(dirs.length > i){
      var dirName = dirs[i];
      if(dirName.length === 0){
        i+=1;
        continue;
      }
      console.log(dirName);
      browser.$('span.jp-DirListing-itemText=' + dirName).scrollIntoView();
      browser.$('span.jp-DirListing-itemText=' + dirName).doubleClick();
      browser.pause(1500);
      i+=1;
    }
    this.increaseWindowWidth(200);
  };

  this.increaseWindowWidth = function (addWidth) {
    var curSize = browser.getWindowSize();
    browser.setWindowSize(curSize.width + addWidth, curSize.height);
  };

  this.clickSaveNotebook = function () {
    browser.$('div=File').click();
    var saveMenuItem = browser.$$('li[data-command="docmanager:save"]')[1];
    saveMenuItem.waitForEnabled();
    saveMenuItem.click();

  };

  /* Close and Shutdown Notebook */
  this.closeAndHaltNotebook = function () {
    this.clickCellAllOutputClear;
    browser.$('div=File').click();
    var closeAndCleanupMenuItem = browser.$('li[data-command="filemenu:close-and-cleanup"]');
    closeAndCleanupMenuItem.waitForEnabled();
    closeAndCleanupMenuItem.click();
    var acceptDialogButton = browser.$('button.jp-Dialog-button.jp-mod-accept.jp-mod-warn.jp-mod-styled');
    acceptDialogButton.waitForEnabled();
    acceptDialogButton.click();
    browser.waitUntil(function(){
      return browser.$$('li[data-type="document-title"]').length < 1;
    }, 10000);
    browser.pause(5000);
  };

  this.saveAndCloseNotebook = function () {
    this.clickCellAllOutputClear;
    this.clickSaveNotebook();
    browser.$('div=File').click();
    var closeAndCleanupMenuItem = browser.$('li[data-command="filemenu:close-and-cleanup"]');
    closeAndCleanupMenuItem.waitForEnabled();
    closeAndCleanupMenuItem.click();
    var acceptDialogButton = browser.$('button.jp-Dialog-button.jp-mod-accept.jp-mod-warn.jp-mod-styled');
    acceptDialogButton.waitForEnabled();
    acceptDialogButton.click();
    browser.waitUntil(function(){
      return browser.$$('li[data-type="document-title"]').length < 2;
    });
  };

  this.clickCellAllOutputClear = function() {
    browser.$('div=Edit').click();
    var clearAllOutputsMenuItem = browser.$('li[data-command="editmenu:clear-all"]');
    clearAllOutputsMenuItem.waitForEnabled();
    clearAllOutputsMenuItem.click();
  };

  this.getCodeCellByIndex = function (index) {
    return $$('div.jp-Cell.jp-CodeCell.jp-Notebook-cell')[index];
  };

  this.clickRunCell = function () {
    browser.waitUntil(function(){
      return browser.$$('div.jp-NotebookPanel-toolbar > div.jp-ToolbarButton').length > 1;
    });
    var buttonRunCell = browser.$$('div.jp-NotebookPanel-toolbar > div.jp-ToolbarButton')[5];
    buttonRunCell.click();
    this.kernelIdleIcon.waitForEnabled();
  };

  this.clickRunCellWithoutWaiting = function () {
    browser.$('button.jp-ToolbarButtonComponent > span.jp-RunIcon').click();
  };

  this.clickRunAllCells = function() {
    browser.$('div=Run').click();
    var runAllCellsMenuItem = browser.$('li[data-command="runmenu:run-all"]');
    runAllCellsMenuItem.waitForEnabled();
    runAllCellsMenuItem.click();
  };

  this.clickDialogPublishButton = function(){
    browser.$('div.jp-Dialog-buttonLabel=Publish').click();
  };

  this.clickInterruptKernel = function () {
    browser.$('button.jp-ToolbarButtonComponent > span.jp-StopIcon').click();
  };

  this.getAllOutputAreaChildren = function (codeCell, isWait) {
    if(isWait){
      browser.waitUntil(function(){
        return codeCell.$$('div.jp-OutputArea-child').length > 0;
      });
    }
    else {
      browser.pause(1000);
    }
    return codeCell.$$('div.jp-OutputArea-child');
  };

  this.getAllOutputsExecuteResult = function (codeCell) {
    browser.waitUntil(function(){
      return codeCell.$$('div.jp-OutputArea-child.jp-OutputArea-executeResult > div.jp-OutputArea-output').length > 0;
    });
    return codeCell.$$('div.jp-OutputArea-child.jp-OutputArea-executeResult > div.jp-OutputArea-output');
  };

  this.getAllOutputsStdout = function (codeCell) {
    browser.waitUntil(function(){
      return codeCell.$$('div.jp-OutputArea-child > div.jp-OutputArea-output[data-mime-type="application/vnd.jupyter.stdout"]').length > 0;
    });
    return codeCell.$$('div.jp-OutputArea-child > div.jp-OutputArea-output[data-mime-type="application/vnd.jupyter.stdout"]');
  };

  this.getAllOutputsStderr = function (codeCell) {
    browser.waitUntil(function(){
      return codeCell.$$('div.jp-OutputArea-child > div.jp-OutputArea-output[data-mime-type="application/vnd.jupyter.stderr"]').length > 0;
    });
    return codeCell.$$('div.jp-OutputArea-child > div.jp-OutputArea-output[data-mime-type="application/vnd.jupyter.stderr"]');
  };

  this.getAllOutputsHtmlType = function (codeCell) {
    browser.waitUntil(function(){
      return codeCell.$$('div.jp-OutputArea-child > div.jp-OutputArea-output[data-mime-type="text/html"]').length > 0;
    });
    return codeCell.$$('div.jp-OutputArea-child > div.jp-OutputArea-output[data-mime-type="text/html"]');
  };

  this.getAllOutputsWidget = function(codeCell){
    browser.waitUntil(function(){
      return codeCell.$$('div.jp-OutputArea-child > div.jp-OutputArea-output').length > 0;
    });
    return codeCell.$$('div.jp-OutputArea-child > div.jp-OutputArea-output');
  };

  this.callAutocompleteAndGetItsList = function(codeCell, codeStr){
    codeCell.scrollIntoView();
    codeCell.$('div.CodeMirror.cm-s-jupyter').click();
    codeCell.keys(codeStr);
    browser.keys("Tab");
    browser.keys('\uE000');
    browser.waitUntil(function() {
      return browser.$('ul.jp-Completer').isDisplayed()
    }, 10000, 'autocomplete list is not visible');
    return $$('li.jp-Completer-item');
  };

  this.callDocAndGetItsTooltip = function(codeCell, codeStr){
    codeCell.scrollIntoView();
    codeCell.$('div.CodeMirror.cm-s-jupyter').click();
    codeCell.keys(codeStr);
    browser.keys(["Shift", "Tab"]);
    browser.keys('\uE000');
    browser.waitUntil(function() {
      return browser.$('div.jp-Tooltip').isDisplayed();
    }, 10000, 'doc tooltip is not visible');
    return $('div.jp-Tooltip-content');
  };

  this.openUIWindow = function(){
    browser.$$('li[data-id="command-palette"]')[0].click();
    browser.$('div.p-CommandPalette-itemLabel=BeakerX Options').click();
    browser.$$('ul.p-TabBar-content')[2].click('li[data-id="beakerx-tree-widget"]');
  };

  this.getJupyterWidget = function(codeCell){
    return codeCell.$('div.jupyter-widgets > div.jupyter-widgets');
  };

  this.switchToNotebookWindow = function(){
    browser.switchWindow('JupyterLab');
  };

};
module.exports = LabPageObject;
