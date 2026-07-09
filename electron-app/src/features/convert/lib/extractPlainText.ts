// Сериализация отредактированного HTML-предпросмотра в плоский текст для
// /analyze-text — СТРОГО в формате `_extract_text_from_docx` анализатора
// (python-backend/app/document_analyzer.py), иначе label-anchored паттерны
// разбора промахиваются. Контракт формата:
//   1) сначала весь НЕ-табличный контент: каждый блок (абзац/заголовок/пункт
//      списка) — отдельной строкой, пустые пропускаются;
//   2) затем ВСЕ таблицы поячеечно: каждая непустая ячейка — отдельным
//      элементом, БЕЗ разделителей столбцов/строк (внутренние переносы ячейки
//      сохраняются — так делает python-docx `cell.text`);
//   3) всё соединяется через '\n'.
// Порядок «абзацы, потом таблицы» повторяет python-docx (doc.paragraphs,
// затем doc.tables), а не документный порядок.

/** Теги, которые считаем самостоятельными текстовыми блоками вне таблиц. */
const BLOCK_SELECTOR = 'p, h1, h2, h3, h4, h5, h6, li, div';

/**
 * Текст элемента с учётом <br> как переноса строки (textContent их глотает).
 * contentEditable вставляет <br> при Shift+Enter и в пустых строках.
 */
function blockText(el: Element): string {
  let out = '';
  const walk = (node: Node): void => {
    if (node.nodeType === Node.TEXT_NODE) {
      out += node.textContent ?? '';
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    if ((node as Element).tagName === 'BR') {
      out += '\n';
      return;
    }
    node.childNodes.forEach(walk);
  };
  walk(el);
  return out;
}

/** Блок является «листовым» (не содержит вложенных блочных элементов). */
function isLeafBlock(el: Element): boolean {
  return el.querySelector('p, h1, h2, h3, h4, h5, h6, li, div, table') === null;
}

/**
 * Извлекает плоский текст из корня предпросмотра (contentEditable-области).
 * Чистая функция DOM → строка; используется по кнопке «Далее» convert-шага.
 */
export function extractPlainText(root: HTMLElement): string {
  const parts: string[] = [];

  // 1. Не-табличный контент: листовые блоки вне таблиц, построчно.
  root.querySelectorAll(BLOCK_SELECTOR).forEach((el) => {
    if (el.closest('table')) return; // ячейки собираем отдельным проходом
    if (!isLeafBlock(el)) return; // контейнер — его текст дадут вложенные блоки
    blockText(el)
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .forEach((line) => parts.push(line));
  });

  // 2. Таблицы: каждая непустая ячейка — отдельным элементом (как cell.text
  //    в python-docx: абзацы внутри ячейки склеены '\n', затем strip).
  root.querySelectorAll('table').forEach((table) => {
    table.querySelectorAll('td, th').forEach((cell) => {
      // Абзацы ячейки соединяем '\n' (а не пробелом), как python-docx
      const cellBlocks: string[] = [];
      const leafBlocks = Array.from(cell.querySelectorAll(BLOCK_SELECTOR)).filter(isLeafBlock);
      if (leafBlocks.length > 0) {
        leafBlocks.forEach((b) => cellBlocks.push(blockText(b)));
      } else {
        cellBlocks.push(blockText(cell));
      }
      const text = cellBlocks.join('\n').trim();
      if (text) parts.push(text);
    });
  });

  return parts.join('\n');
}
