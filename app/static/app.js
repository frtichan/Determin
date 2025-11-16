// デフォルトのDSL
const defaultDSL = {
  steps: [
    { op: "regex_extract", column: "line", pattern: "\\d+$", group: 0, as: "trailing_number" },
    { op: "select", columns: ["trailing_number"] }
  ]
};

let currentDSL = JSON.parse(JSON.stringify(defaultDSL)); // Deep copy
let chatHistory = [];
let currentRecipeId = null; // 現在読み込んでいるレシピID
let currentSortMode = 'used'; // 'used' or 'created'

// レシピを読み込んだ時の状態を保存（変更検知用）
let loadedDSL = null;
let loadedChatHistory = null;

async function runPreview() {
  const inputData = document.getElementById('inputData').value;
  const resultBox = document.getElementById('resultBox');
  const resultMeta = document.getElementById('resultMeta');
  const resultTable = document.getElementById('resultTable');
  const resultError = document.getElementById('resultError');

  resultError.hidden = true;
  resultTable.innerHTML = '';
  resultMeta.innerText = '';
  resultBox.hidden = false;

  const payload = {
    dsl: currentDSL,
    input: {
      data: inputData
    }
  };

  try {
    const resp = await fetch('/runs/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    if (!resp.ok) {
      resultError.hidden = false;
      resultError.innerText = data.detail || 'エラーが発生しました';
      return;
    }
    const rows = data.output || [];
    const columns = data.meta?.columns || Object.keys(rows[0] || {});
    resultMeta.innerText = columns.length > 1 ? `行数: ${rows.length} / 列: ${columns.join(', ')}` : `行数: ${rows.length}`;
    renderTable(resultTable, columns, rows);
  } catch (e) {
    resultError.hidden = false;
    resultError.innerText = '通信に失敗しました: ' + e.message;
  }
}

async function askAI() {
  const chatInput = document.getElementById('chatInput');
  const instruction = chatInput.value || '';
  const inputData = document.getElementById('inputData').value;
  const expectedData = document.getElementById('expectedData').value;
  const resultError = document.getElementById('resultError');
  const resultBox = document.getElementById('resultBox');
  const resultMeta = document.getElementById('resultMeta');
  const chatLog = document.getElementById('chatLog');
  resultError.hidden = true;
  resultBox.hidden = false;

  if (instruction.trim().length < 3) {
    resultError.hidden = false;
    resultError.innerText = 'AIへのお願いは3文字以上で入力してください。';
    return;
  }

  try {
    // Append user message to history & UI
    chatHistory.push({ role: 'user', content: instruction });
    appendChatBubble('me', 'you', instruction);

    const payload = {
      instruction,
      sample_input: inputData,
      mask: false,
      previous_dsl: currentDSL,
      history: chatHistory
    };
    if (expectedData.trim().length > 0) {
      payload.expected_output = expectedData;
    }
    const resp = await fetch('/ai/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    console.log('AI Response:', data); // デバッグ用
    if (!resp.ok) {
      resultError.hidden = false;
      resultError.innerText = data.detail || 'AI相談に失敗しました';
      return;
    }
    currentDSL = data.dsl || currentDSL;
    console.log('AI Response data:', data); // デバッグ用：全体のレスポンスを確認
    console.log('Updated DSL:', currentDSL); // デバッグ用
    console.log('Has excel_formula:', !!data.excel_formula); // デバッグ用
    console.log('Has dsl:', !!data.dsl); // デバッグ用
    
    if (data.explanation) {
      resultMeta.innerText = 'AI説明: ' + data.explanation;
    }
    const assistantText = data.explanation || 'アルゴリズムを更新しました。';
    
    // チャット履歴にExcel数式とDSL情報も含めて保存
    // 注意: data.dslが存在しない場合でも、現在有効なcurrentDSLを保存する
    const assistantMessage = { 
      role: 'assistant', 
      content: assistantText,
      excel_formula: data.excel_formula || null,
      dsl: currentDSL  // 常に現在有効なDSLを保存
    };
    chatHistory.push(assistantMessage);
    
    appendChatBubble('ai', 'assistant', assistantText);

    // Append Excel formula if available
    if (data.excel_formula) {
      console.log('Appending Excel formula'); // デバッグ用
      appendExcelFormula(data.excel_formula);
    }

    // Append collapsible DSL viewer
    if (data.dsl) {
      console.log('Appending DSL:', data.dsl); // デバッグ用
      appendDSL(data.dsl);
    } else {
      console.log('No DSL in response, skipping DSL display'); // デバッグ用
    }
    
    // デバッグ情報を表示（デバッグモードがオンの場合のみ）
    // リクエスト情報も含めて保存
    data._request = {
      instruction: instruction,
      sample_input: inputData,
      previous_dsl: payload.previous_dsl,
      expected_output: expectedData.trim().length > 0 ? expectedData : null,
      history: chatHistory.slice(0, -1) // 今回追加した分を除く
    };
    appendDebugInfo(data);

    // Optional: append compact validation info
    // Show validation result if any
    if (data.validation) {
      const v = data.validation;
      const note = document.createElement('div');
      note.className = 'muted';
      note.innerText = v.matches ? '期待された出力と一致しました。' : ('期待と不一致: ' + (v.detail || ''));
      chatLog.appendChild(note);
    }
    // Scroll to bottom
    chatLog.scrollTop = chatLog.scrollHeight;
    // Clear input
    chatInput.value = '';
    await runPreview();
  } catch (e) {
    resultError.hidden = false;
    resultError.innerText = '通信に失敗しました: ' + e.message;
  }
}

function renderTable(container, columns, rows) {
  if (!columns.length) {
    container.innerHTML = '<div class=\"muted\">表示する列がありません</div>';
    return;
  }
  const table = document.createElement('table');
  const hideHeader = document.getElementById('hideHeaderToggle')?.checked === true;
  // ヘッダーを表示：hideHeaderがfalseで、かつ列が複数ある場合
  if (!hideHeader && columns.length > 1) {
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    for (const c of columns) {
      const th = document.createElement('th');
      th.innerText = c;
      trh.appendChild(th);
    }
    thead.appendChild(trh);
    table.appendChild(thead);
  }
  const tbody = document.createElement('tbody');
  for (const row of rows) {
    const tr = document.createElement('tr');
    for (const c of columns) {
      const td = document.createElement('td');
      const v = row[c];
      td.innerText = v === null || v === undefined ? '' : String(v);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  container.innerHTML = '';
  container.appendChild(table);
}

function appendChatBubble(cssClass, role, text) {
  const chatLog = document.getElementById('chatLog');
  const div = document.createElement('div');
  div.className = 'chat-bubble ' + cssClass;
  const roleEl = document.createElement('span');
  roleEl.className = 'chat-role'; roleEl.innerText = role + ':';
  const content = document.createElement('span');
  content.innerText = text;
  div.appendChild(roleEl); div.appendChild(content);
  chatLog.appendChild(div);
}

// Excel数式を表示する関数
function appendExcelFormula(excelFormula) {
  const chatLog = document.getElementById('chatLog');
  const excelDiv = document.createElement('div');
  excelDiv.className = 'excel-formula-box';
  excelDiv.style.cssText = 'background: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; padding: 12px; margin: 8px 0; max-width: 100%; overflow: hidden; word-wrap: break-word; overflow-wrap: break-word;';
  
  const title = document.createElement('div');
  title.style.cssText = 'font-weight: 600; color: #059669; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;';
  title.innerHTML = '📊 Excel数式';
  excelDiv.appendChild(title);
  
  // Handle both object and string formats
  const formula = typeof excelFormula === 'string' 
    ? { formula: excelFormula, description: null, notes: null }
    : excelFormula;
  
  // Display formula if available
  if (formula.formula) {
    const formulas = Array.isArray(formula.formula) ? formula.formula : [formula.formula];
    const columns = formula.columns || [];
    
        formulas.forEach((f, idx) => {
          const formulaContainer = document.createElement('div');
          formulaContainer.style.cssText = 'background: #ffffff; border: 1px solid #d1d5db; border-radius: 6px; padding: 10px; margin-bottom: 8px; max-width: 100%; overflow: hidden;';
          
          // Show column label if available
          if (columns[idx]) {
            const columnLabel = document.createElement('div');
            columnLabel.style.cssText = 'font-size: 0.85em; color: #059669; margin-bottom: 4px; font-weight: 600; word-wrap: break-word; overflow-wrap: break-word;';
            columnLabel.textContent = columns[idx];
            formulaContainer.appendChild(columnLabel);
          }
          
          const formulaCode = document.createElement('code');
          formulaCode.style.cssText = 'white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; display: block; font-family: "Consolas", "Monaco", monospace; font-size: 0.9em; color: #1a1a1a; max-width: 100%;';
          formulaCode.textContent = f;
      
      formulaContainer.appendChild(formulaCode);
      excelDiv.appendChild(formulaContainer);
      
      const copyBtn = document.createElement('button');
      copyBtn.textContent = columns[idx] ? `${columns[idx]}をコピー` : '数式をコピー';
      copyBtn.style.cssText = 'padding: 6px 12px; font-size: 0.85em; margin-bottom: 8px;';
      copyBtn.onclick = () => {
        navigator.clipboard.writeText(f);
        const originalText = copyBtn.textContent;
        copyBtn.textContent = 'コピーしました！';
        setTimeout(() => { copyBtn.textContent = originalText; }, 2000);
      };
      excelDiv.appendChild(copyBtn);
    });
  }
  
  // Display description
  if (formula.description) {
    const desc = document.createElement('div');
    desc.style.cssText = 'font-size: 0.9em; margin-top: 8px; line-height: 1.5; color: var(--text); word-wrap: break-word; overflow-wrap: break-word;';
    desc.textContent = formula.description;
    excelDiv.appendChild(desc);
  }
  
  // Display notes if available
  if (formula.notes) {
    const notes = document.createElement('div');
    notes.style.cssText = 'font-size: 0.85em; color: var(--muted); margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(16, 185, 129, 0.2); word-wrap: break-word; overflow-wrap: break-word;';
    notes.textContent = '💡 ' + formula.notes;
    excelDiv.appendChild(notes);
  }
  
  chatLog.appendChild(excelDiv);
}

// DSLを表示する関数
function appendDSL(dsl) {
  const chatLog = document.getElementById('chatLog');
  const d = document.createElement('details');
  d.className = 'chat-dsl';
  d.style.cssText = 'max-width: 100%; overflow: hidden;';
  const s = document.createElement('summary');
  s.innerText = '提案されたDSLを表示';
  const pre = document.createElement('pre');
  pre.textContent = JSON.stringify(dsl, null, 2);
  d.appendChild(s);
  d.appendChild(pre);
  chatLog.appendChild(d);
}

// デバッグ情報を表示する関数
function appendDebugInfo(data) {
  const debugModeToggle = document.getElementById('debugModeToggle');
  if (!debugModeToggle || !debugModeToggle.checked) {
    return; // デバッグモードがオフの場合は表示しない
  }
  
  const chatLog = document.getElementById('chatLog');
  const debugDiv = document.createElement('div');
  debugDiv.className = 'debug-info';
  
  const title = document.createElement('div');
  title.className = 'debug-info-title';
  title.innerHTML = '🔍 デバッグ情報（AI応答の生データ）';
  debugDiv.appendChild(title);
  
  // リクエスト情報
  const requestSection = document.createElement('details');
  requestSection.style.cssText = 'margin-bottom: 8px; max-width: 100%; overflow: hidden;';
  const requestSummary = document.createElement('summary');
  requestSummary.textContent = 'リクエスト情報';
  requestSummary.style.cssText = 'cursor: pointer; color: #b45309; font-weight: 600;';
  requestSection.appendChild(requestSummary);
  
  const requestPre = document.createElement('pre');
  requestPre.textContent = JSON.stringify({
    instruction: data._request?.instruction || 'N/A',
    sample_input: data._request?.sample_input || 'N/A',
    previous_dsl: data._request?.previous_dsl || null,
    expected_output: data._request?.expected_output || null,
    history_length: data._request?.history?.length || 0
  }, null, 2);
  requestSection.appendChild(requestPre);
  debugDiv.appendChild(requestSection);
  
  // レスポンス情報
  const responseSection = document.createElement('details');
  responseSection.open = true;
  responseSection.style.cssText = 'max-width: 100%; overflow: hidden;';
  const responseSummary = document.createElement('summary');
  responseSummary.textContent = 'レスポンス情報（全体）';
  responseSummary.style.cssText = 'cursor: pointer; color: #b45309; font-weight: 600;';
  responseSection.appendChild(responseSummary);
  
  const responsePre = document.createElement('pre');
  // _request プロパティは除外して表示
  const responseData = {...data};
  delete responseData._request;
  responsePre.textContent = JSON.stringify(responseData, null, 2);
  responseSection.appendChild(responsePre);
  debugDiv.appendChild(responseSection);
  
  // フィールド別の詳細
  const fieldsDiv = document.createElement('div');
  fieldsDiv.style.cssText = 'margin-top: 8px; max-width: 100%; overflow: hidden;';
  fieldsDiv.innerHTML = `
    <div style="font-size: 0.9em; color: #b45309; margin-bottom: 4px;">
      <strong>含まれるフィールド:</strong>
    </div>
    <div style="display: flex; flex-wrap: wrap; gap: 6px; word-wrap: break-word; overflow-wrap: break-word;">
      ${Object.keys(responseData).map(key => {
        const hasValue = responseData[key] !== null && responseData[key] !== undefined;
        return `<span style="padding: 2px 8px; background: ${hasValue ? '#10b981' : '#6b7280'}; color: white; border-radius: 4px; font-size: 0.8em; word-break: break-word;">${key}</span>`;
      }).join('')}
    </div>
  `;
  debugDiv.appendChild(fieldsDiv);
  
  chatLog.appendChild(debugDiv);
}

// レシピ管理機能
async function loadRecipes() {
  try {
    const resp = await fetch(`/recipes/?sort=${currentSortMode}`);
    const data = await resp.json();
    const recipeList = document.getElementById('recipeList');
    recipeList.innerHTML = '';
    
    if (data.items.length === 0) {
      recipeList.innerHTML = '<div class="muted">保存されたレシピはありません</div>';
      return;
    }
    
    for (const recipe of data.items) {
      const item = document.createElement('div');
      item.className = 'recipe-item';
      if (recipe.id === currentRecipeId) {
        item.classList.add('active');
      }
      
      const nameDiv = document.createElement('div');
      nameDiv.className = 'recipe-name';
      nameDiv.innerText = recipe.name;
      nameDiv.title = recipe.name; // ツールチップで全文表示
      
      const metaDiv = document.createElement('div');
      metaDiv.className = 'recipe-meta';
      const formatDate = (dateStr) => {
        const d = new Date(dateStr);
        const now = new Date();
        const diff = now - d;
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        
        if (days === 0) return '今日';
        if (days === 1) return '昨日';
        if (days < 7) return `${days}日前`;
        return d.toLocaleDateString('ja-JP', { month: 'short', day: 'numeric' });
      };
      
      const timeInfo = recipe.last_used_at 
        ? formatDate(recipe.last_used_at)
        : formatDate(recipe.created_at);
      metaDiv.innerText = timeInfo;
      
      const actionsDiv = document.createElement('div');
      actionsDiv.className = 'recipe-actions';
      
      // 三点ボタン
      const optionsBtn = document.createElement('button');
      optionsBtn.innerText = '⋯';
      optionsBtn.className = 'recipe-options-btn';
      optionsBtn.title = 'オプション';
      optionsBtn.onclick = (e) => {
        e.stopPropagation();
        toggleRecipeMenu(actionsDiv, recipe, item);
      };
      
      actionsDiv.appendChild(optionsBtn);
      
      item.appendChild(nameDiv);
      item.appendChild(metaDiv);
      item.appendChild(actionsDiv);
      
      item.onclick = () => loadRecipe(recipe.id);
      
      recipeList.appendChild(item);
    }
  } catch (e) {
    console.error('Failed to load recipes:', e);
  }
}

async function loadRecipe(recipeId) {
  // 作業中の内容がある場合は確認
  if (hasUnsavedChanges()) {
    if (!confirm('作業中の内容が失われますが、別のレシピを読み込んでもよろしいですか？')) {
      return;
    }
  }
  
  try {
    const resp = await fetch(`/recipes/${recipeId}`);
    if (!resp.ok) throw new Error('レシピの読み込みに失敗しました');
    const data = await resp.json();
    
    currentRecipeId = recipeId;
    currentDSL = data.dsl;
    
    // 読み込んだ時点の状態を保存（変更検知用）
    loadedDSL = JSON.parse(JSON.stringify(data.dsl));
    loadedChatHistory = data.chat_history ? JSON.parse(JSON.stringify(data.chat_history)) : [];
    
    // チャットログをクリア
    const chatLog = document.getElementById('chatLog');
    chatLog.innerHTML = '';
    
    // チャット履歴を復元
    if (data.chat_history && Array.isArray(data.chat_history)) {
      chatHistory = data.chat_history;
      
      for (const msg of chatHistory) {
        if (msg.role === 'user') {
          appendChatBubble('me', 'you', msg.content);
        } else if (msg.role === 'assistant') {
          appendChatBubble('ai', 'assistant', msg.content);
          
          // Excel数式がある場合は表示
          if (msg.excel_formula) {
            appendExcelFormula(msg.excel_formula);
          }
          
          // DSLがある場合は表示
          if (msg.dsl) {
            appendDSL(msg.dsl);
          }
        }
      }
      
      // 最新の会話までスクロール
      chatLog.scrollTop = chatLog.scrollHeight;
    } else {
      chatHistory = [];
    }
    
    // UI更新
    document.getElementById('currentRecipeInfo').innerText = 
      `現在のレシピ: ${data.name}`;
    document.getElementById('updateBtn').disabled = false;
    document.getElementById('saveAsBtn').disabled = false;
    
    // レシピリストの選択状態を更新
    document.querySelectorAll('.recipe-item').forEach(item => {
      item.classList.remove('active');
    });
    event?.target?.closest('.recipe-item')?.classList.add('active');
    
    await loadRecipes(); // リストを再読み込みして選択状態を反映
  } catch (e) {
    alert('レシピの読み込みに失敗しました: ' + e.message);
  }
}

async function deleteRecipe(recipeId) {
  try {
    const resp = await fetch(`/recipes/${recipeId}`, { method: 'DELETE' });
    if (!resp.ok) throw new Error('削除に失敗しました');
    
    if (currentRecipeId === recipeId) {
      currentRecipeId = null;
      document.getElementById('currentRecipeInfo').innerText = '';
      document.getElementById('updateBtn').disabled = true;
      document.getElementById('saveAsBtn').disabled = true;
    }
    
    await loadRecipes();
  } catch (e) {
    alert('削除に失敗しました: ' + e.message);
  }
}

async function renameRecipe(recipeId, currentName, recipeItem) {
  // レシピアイテムをインライン編集モードに変更
  const nameDiv = recipeItem.querySelector('.recipe-name');
  const originalHTML = nameDiv.innerHTML;
  
  const editDiv = document.createElement('div');
  editDiv.className = 'recipe-name-edit';
  
  const input = document.createElement('input');
  input.type = 'text';
  input.value = currentName;
  input.style.width = '100%';
  
  const actionsDiv = document.createElement('div');
  actionsDiv.className = 'recipe-name-edit-actions';
  
  const saveBtn = document.createElement('button');
  saveBtn.textContent = '保存';
  saveBtn.style.background = '#10b981';
  saveBtn.onclick = async (e) => {
    e.stopPropagation();
    const newName = input.value.trim();
    if (!newName || newName === currentName) {
      nameDiv.innerHTML = originalHTML;
      return;
    }
    
    try {
      const resp = await fetch(`/recipes/${recipeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName })
      });
      if (!resp.ok) throw new Error('名前変更に失敗しました');
      
      if (currentRecipeId === recipeId) {
        document.getElementById('currentRecipeInfo').innerText = `現在のレシピ: ${newName}`;
      }
      
      await loadRecipes();
    } catch (e) {
      alert('名前変更に失敗しました: ' + e.message);
      nameDiv.innerHTML = originalHTML;
    }
  };
  
  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = 'キャンセル';
  cancelBtn.style.background = '#6b7280';
  cancelBtn.onclick = (e) => {
    e.stopPropagation();
    nameDiv.innerHTML = originalHTML;
  };
  
  actionsDiv.appendChild(saveBtn);
  actionsDiv.appendChild(cancelBtn);
  editDiv.appendChild(input);
  editDiv.appendChild(actionsDiv);
  
  nameDiv.innerHTML = '';
  nameDiv.appendChild(editDiv);
  input.focus();
  input.select();
  
  // Enterキーで保存
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      saveBtn.click();
    } else if (e.key === 'Escape') {
      cancelBtn.click();
    }
  });
}

function toggleRecipeMenu(actionsDiv, recipe, recipeItem) {
  // 既存のメニューを閉じる
  document.querySelectorAll('.recipe-dropdown-menu').forEach(menu => menu.remove());
  document.querySelectorAll('.recipe-actions.active').forEach(actions => {
    actions.classList.remove('active');
  });
  
  // このアクションボタンを常に表示する
  actionsDiv.classList.add('active');
  
  // ドロップダウンメニューを作成
  const menu = document.createElement('div');
  menu.className = 'recipe-dropdown-menu';
  
  // 名前を変更ボタン
  const renameBtn = document.createElement('button');
  renameBtn.innerHTML = '✏️ 名前を変更';
  renameBtn.onclick = (e) => {
    e.stopPropagation();
    actionsDiv.classList.remove('active');
    menu.remove();
    renameRecipe(recipe.id, recipe.name, recipeItem);
  };
  
  // 削除ボタン
  const deleteBtn = document.createElement('button');
  deleteBtn.className = 'danger';
  deleteBtn.innerHTML = '🗑️ 削除';
  deleteBtn.onclick = async (e) => {
    e.stopPropagation();
    actionsDiv.classList.remove('active');
    menu.remove();
    if (!confirm(`レシピ「${recipe.name}」を削除しますか？`)) return;
    await deleteRecipe(recipe.id);
  };
  
  menu.appendChild(renameBtn);
  menu.appendChild(deleteBtn);
  actionsDiv.appendChild(menu);
  
  // メニュー外をクリックしたら閉じる
  setTimeout(() => {
    document.addEventListener('click', function closeMenu(e) {
      if (!menu.contains(e.target)) {
        actionsDiv.classList.remove('active');
        menu.remove();
        document.removeEventListener('click', closeMenu);
      }
    });
  }, 0);
}

async function updateRecipe() {
  if (!currentRecipeId) return;
  
  try {
    const resp = await fetch(`/recipes/${currentRecipeId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        dsl: currentDSL,
        chat_history: chatHistory 
      })
    });
    if (!resp.ok) throw new Error('更新に失敗しました');
    
    // 上書き保存した時点の状態を記録（変更検知用）
    loadedDSL = JSON.parse(JSON.stringify(currentDSL));
    loadedChatHistory = JSON.parse(JSON.stringify(chatHistory));
    
    alert('レシピを上書き保存しました');
    await loadRecipes();
  } catch (e) {
    alert('更新に失敗しました: ' + e.message);
  }
}

async function saveAsNewRecipe() {
  showRecipeNameInput('saveAs');
}

// レシピ名入力UIを表示
let currentSaveMode = 'new'; // 'new' or 'saveAs'

function showRecipeNameInput(mode) {
  currentSaveMode = mode;
  const inputDiv = document.getElementById('recipeNameInput');
  const inputField = document.getElementById('recipeNameField');
  
  inputField.value = '';
  inputDiv.style.display = 'block';
  inputField.focus();
  
  // ラベルを変更
  const label = inputDiv.querySelector('label');
  if (mode === 'saveAs') {
    label.textContent = '新しいレシピ名';
  } else {
    label.textContent = 'レシピ名';
  }
}

function hideRecipeNameInput() {
  const inputDiv = document.getElementById('recipeNameInput');
  const inputField = document.getElementById('recipeNameField');
  inputDiv.style.display = 'none';
  inputField.value = '';
}

async function confirmSaveRecipe() {
  const inputField = document.getElementById('recipeNameField');
  const name = inputField.value.trim();
  
  if (!name) {
    alert('レシピ名を入力してください');
    return;
  }
  
  try {
    const resp = await fetch('/recipes/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        name, 
        dsl: currentDSL,
        chat_history: chatHistory 
      })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || '保存に失敗しました');
    
    currentRecipeId = data.recipe_id;
    document.getElementById('currentRecipeInfo').innerText = `現在のレシピ: ${name}`;
    document.getElementById('updateBtn').disabled = false;
    document.getElementById('saveAsBtn').disabled = false;
    
    // 保存した時点の状態を記録（変更検知用）
    loadedDSL = JSON.parse(JSON.stringify(currentDSL));
    loadedChatHistory = JSON.parse(JSON.stringify(chatHistory));
    
    hideRecipeNameInput();
    alert(currentSaveMode === 'saveAs' ? '別名で保存しました' : '保存しました');
    await loadRecipes();
  } catch (e) {
    alert('保存に失敗しました: ' + e.message);
  }
}

// 作業中かどうかを判定
function hasUnsavedChanges() {
  // レシピが読み込まれている場合
  if (currentRecipeId !== null) {
    // 読み込んだ時点からDSLが変更されているか
    const dslChanged = JSON.stringify(currentDSL) !== JSON.stringify(loadedDSL);
    
    // 読み込んだ時点からチャット履歴が変更されているか
    const chatChanged = JSON.stringify(chatHistory) !== JSON.stringify(loadedChatHistory);
    
    return dslChanged || chatChanged;
  }
  
  // 新規作成の場合：DSLがデフォルトと異なるか、チャット履歴があるか
  const dslChanged = JSON.stringify(currentDSL) !== JSON.stringify(defaultDSL);
  const hasChat = chatHistory.length > 0;
  
  return dslChanged || hasChat;
}

// 新規レシピを作成
function createNewRecipe() {
  // 作業中の内容がある場合は確認
  if (hasUnsavedChanges()) {
    if (!confirm('作業中の内容が失われますが、新規作成してもよろしいですか？')) {
      return;
    }
  }
  
  // 状態をリセット
  currentDSL = JSON.parse(JSON.stringify(defaultDSL));
  chatHistory = [];
  currentRecipeId = null;
  loadedDSL = null;
  loadedChatHistory = null;
  
  // UIをクリア
  document.getElementById('chatLog').innerHTML = '';
  document.getElementById('currentRecipeInfo').innerText = '';
  document.getElementById('updateBtn').disabled = true;
  document.getElementById('saveAsBtn').disabled = true;
  
  // 結果ボックスを非表示に
  const resultBox = document.getElementById('resultBox');
  if (resultBox) {
    resultBox.hidden = true;
  }
  
  // レシピリストの選択状態をクリア
  document.querySelectorAll('.recipe-item').forEach(item => {
    item.classList.remove('active');
  });
  
  // 入力欄もリセット（オプション）
  // document.getElementById('inputData').value = '';
  // document.getElementById('realData').value = '';
}

window.addEventListener('DOMContentLoaded', () => {
  const runBtn = document.getElementById('runBtn');
  runBtn?.addEventListener('click', runPreview);
  const aiBtn = document.getElementById('aiBtn');
  aiBtn?.addEventListener('click', askAI);
  const chatInput = document.getElementById('chatInput');
  chatInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      askAI();
    }
  });

  // Recipe management
  loadRecipes(); // 初回読み込み
  
  const refreshRecipesBtn = document.getElementById('refreshRecipesBtn');
  refreshRecipesBtn?.addEventListener('click', loadRecipes);
  
  // 新規作成ボタン
  const newRecipeBtn = document.getElementById('newRecipeBtn');
  newRecipeBtn?.addEventListener('click', createNewRecipe);
  
  // ソート切り替え
  document.querySelectorAll('input[name="sortRecipe"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      currentSortMode = e.target.value;
      loadRecipes();
    });
  });

  // Save current algorithm (新規保存)
  const saveBtn = document.getElementById('saveBtn');
  saveBtn?.addEventListener('click', () => {
    showRecipeNameInput('new');
  });
  
  // レシピ名入力の確定/キャンセル
  const confirmSaveBtn = document.getElementById('confirmSaveBtn');
  confirmSaveBtn?.addEventListener('click', confirmSaveRecipe);
  
  const cancelSaveBtn = document.getElementById('cancelSaveBtn');
  cancelSaveBtn?.addEventListener('click', hideRecipeNameInput);
  
  // Enterキーで保存
  const recipeNameField = document.getElementById('recipeNameField');
  recipeNameField?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      confirmSaveRecipe();
    } else if (e.key === 'Escape') {
      hideRecipeNameInput();
    }
  });
  
  // 上書き保存
  const updateBtn = document.getElementById('updateBtn');
  updateBtn?.addEventListener('click', updateRecipe);
  
  // 別名で保存
  const saveAsBtn = document.getElementById('saveAsBtn');
  saveAsBtn?.addEventListener('click', saveAsNewRecipe);

  // ヘッダー行表示切り替え
  const hideHeaderToggle = document.getElementById('hideHeaderToggle');
  hideHeaderToggle?.addEventListener('change', () => {
    // 現在表示されているテーブルを再描画
    const resultTable = document.getElementById('resultTable');
    if (resultTable && resultTable.innerHTML) {
      // 最後の実行結果を再描画するため、runPreviewを呼ぶ
      // ただし、結果が既にある場合のみ
      const resultBox = document.getElementById('resultBox');
      if (resultBox && !resultBox.hidden) {
        runPreview();
      }
    }
  });

  // Run on real data area
  const runRealBtn = document.getElementById('runRealBtn');
  runRealBtn?.addEventListener('click', async () => {
    const realData = document.getElementById('realData').value;
    const resultError = document.getElementById('resultError');
    const resultBox = document.getElementById('resultBox');
    const resultMeta = document.getElementById('resultMeta');
    const resultTable = document.getElementById('resultTable');
    resultError.hidden = true;
    resultBox.hidden = false;
    try {
      const resp = await fetch('/runs/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dsl: currentDSL, input: { data: realData } })
      });
      const data = await resp.json();
      if (!resp.ok) {
        resultError.hidden = false;
        resultError.innerText = data.detail || 'エラーが発生しました';
        return;
      }
      const rows = data.output || [];
      const columns = data.meta?.columns || Object.keys(rows[0] || {});
      resultMeta.innerText = columns.length > 1 ? `行数: ${rows.length} / 列: ${columns.join(', ')}` : `行数: ${rows.length}`;
      renderTable(resultTable, columns, rows);
    } catch (e) {
      resultError.hidden = false;
      resultError.innerText = '通信に失敗しました: ' + e.message;
    }
  });
});


