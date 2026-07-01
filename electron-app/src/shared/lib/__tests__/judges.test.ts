import { formatJudgeName } from '../judges';

describe('formatJudgeName', () => {
  it('форматирует полное ФИО в «Фамилия И.О.»', () => {
    expect(formatJudgeName('Иванов Иван Иванович')).toBe('Иванов И.И.');
    expect(formatJudgeName('Абдулина Светлана Витальевна')).toBe('Абдулина С.В.');
  });

  it('фамилия + имя (без отчества) → «Фамилия И.»', () => {
    expect(formatJudgeName('Иванов Иван')).toBe('Иванов И.');
  });

  it('одно слово возвращается как есть', () => {
    expect(formatJudgeName('Иванов')).toBe('Иванов');
  });

  it('инициалы в верхнем регистре независимо от исходного', () => {
    expect(formatJudgeName('иванов иван иванович')).toBe('иванов И.И.');
  });

  it('схлопывает лишние пробелы между словами', () => {
    expect(formatJudgeName('Иванов   Иван   Иванович')).toBe('Иванов И.И.');
  });

  it('обрезает ведущие/хвостовые пробелы', () => {
    expect(formatJudgeName('  Иванов Иван Иванович  ')).toBe('Иванов И.И.');
  });

  it('4+ слова: берёт фамилию и инициалы 2-го и 3-го слова', () => {
    expect(formatJudgeName('Иванов Иван Иванович Петрович')).toBe('Иванов И.И.');
  });

  it('пустой/пробельный вход возвращается как есть', () => {
    expect(formatJudgeName('')).toBe('');
    expect(formatJudgeName('   ')).toBe('   ');
  });
});
