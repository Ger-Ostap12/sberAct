import { extractPlainText } from '../extractPlainText';

// Контракт формата — как у `_extract_text_from_docx` анализатора:
// абзацы/заголовки/пункты по строке, ЗАТЕМ ячейки таблиц (каждая непустая —
// отдельной строкой, без разделителей столбцов), всё через '\n'.

function rootFrom(html: string): HTMLElement {
  const div = document.createElement('div');
  div.innerHTML = html;
  return div;
}

describe('extractPlainText', () => {
  it('абзацы и заголовки — по строке, пустые пропущены', () => {
    const root = rootFrom(`
      <h1>ЗАЯВЛЕНИЕ</h1>
      <p>Должник: Иванов Иван Иванович</p>
      <p>   </p>
      <p>ИНН 616100000000</p>
    `);
    expect(extractPlainText(root)).toBe(
      'ЗАЯВЛЕНИЕ\nДолжник: Иванов Иван Иванович\nИНН 616100000000'
    );
  });

  it('таблица идёт ПОСЛЕ абзацев, ячейки поячеечно без разделителей', () => {
    const root = rootFrom(`
      <p>До таблицы</p>
      <table>
        <tr><td>Номер договора</td><td>Дата</td></tr>
        <tr><td>6142027489</td><td></td></tr>
      </table>
      <p>После таблицы</p>
    `);
    // Не-табличный контент собирается первым проходом (включая текст ПОСЛЕ
    // таблицы), затем все ячейки; пустая ячейка пропущена.
    expect(extractPlainText(root)).toBe(
      'До таблицы\nПосле таблицы\nНомер договора\nДата\n6142027489'
    );
  });

  it('пункты списка — отдельными строками', () => {
    const root = rootFrom(`
      <p>Приложения:</p>
      <ul><li>копия договора</li><li>расчёт задолженности</li></ul>
    `);
    expect(extractPlainText(root)).toBe(
      'Приложения:\nкопия договора\nрасчёт задолженности'
    );
  });

  it('<br> внутри блока даёт перенос строки (Shift+Enter в contentEditable)', () => {
    const root = rootFrom('<p>Первая строка<br>Вторая строка</p>');
    expect(extractPlainText(root)).toBe('Первая строка\nВторая строка');
  });

  it('абзацы внутри ячейки склеиваются \\n (как cell.text python-docx)', () => {
    const root = rootFrom(`
      <table><tr><td><p>Строка 1</p><p>Строка 2</p></td></tr></table>
    `);
    expect(extractPlainText(root)).toBe('Строка 1\nСтрока 2');
  });

  it('инлайн-разметка (жирный/курсив) не рвёт строку', () => {
    const root = rootFrom('<p>Сумма <strong>4 463 145 841,47</strong> руб.</p>');
    expect(extractPlainText(root)).toBe('Сумма 4 463 145 841,47 руб.');
  });

  it('div-обёртки не дублируют текст вложенных абзацев', () => {
    const root = rootFrom('<div><p>Только один раз</p></div>');
    expect(extractPlainText(root)).toBe('Только один раз');
  });

  it('пустой корень — пустая строка', () => {
    expect(extractPlainText(rootFrom(''))).toBe('');
  });
});
