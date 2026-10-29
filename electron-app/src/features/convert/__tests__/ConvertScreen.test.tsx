import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConvertScreen from '../ConvertScreen';

// Транспорт — моками: конвертер в тестах не поднимаем
jest.mock('../../../services/electronApi', () => ({
  analyzeDocument: jest.fn(),
  analyzeText: jest.fn(),
  convertAnalyze: jest.fn(),
  convertCancel: jest.fn(),
  convertDownload: jest.fn(),
  convertHealth: jest.fn(),
  convertLog: jest.fn(),
  convertPolish: jest.fn(),
  convertProfile: jest.fn(),
  convertNative: jest.fn(),
  convertScan: jest.fn(),
  convertStatus: jest.fn(),
  converterStart: jest.fn(),
  converterStop: jest.fn(),
  docxText: jest.fn(),
  docxApplyEdits: jest.fn(),
}));

// Тяжёлая панель PDF (pdfjs) в юнит-тестах не рендерится
jest.mock('../PdfPanel', () => () => <div data-testid="pdf-panel" />);

import {
  analyzeDocument,
  analyzeText,
  convertAnalyze,
  convertCancel,
  convertDownload,
  convertHealth,
  convertLog,
  convertNative,
  convertPolish,
  convertProfile,
  convertScan,
  convertStatus,
  converterStart,
  converterStop,
  docxText,
} from '../../../services/electronApi';

const mockStart = converterStart as jest.Mock;
const mockAnalyze = convertAnalyze as jest.Mock;
const mockScan = convertScan as jest.Mock;
const mockStatus = convertStatus as jest.Mock;
const mockDownload = convertDownload as jest.Mock;
const mockAnalyzeDocument = analyzeDocument as jest.Mock;
const mockAnalyzeText = analyzeText as jest.Mock;
const mockStop = converterStop as jest.Mock;
const mockDocxText = docxText as jest.Mock;

const pdfFile = new File([new Uint8Array([1, 2, 3])], 'скан.pdf', {
  type: 'application/pdf',
});

// Галочки настроек распознавания завёрнуты в Tooltip, и он перетягивает на
// себя доступное имя — ищем по подписи и берём вход внутри её label.
const findFlagCheckbox = async (title: RegExp): Promise<HTMLInputElement> => {
  const label = await screen.findByText(title);
  const input = label.closest('label')?.querySelector('input[type="checkbox"]');
  if (!input) throw new Error(`Не найдена галочка «${title}»`);
  return input as HTMLInputElement;
};

beforeEach(() => {
  window.localStorage.clear(); // профиль и дефолт доочистки берутся оттуда
  jest.clearAllMocks();
  mockStart.mockResolvedValue({ ok: true });
  mockStop.mockResolvedValue({ ok: true });
  // Окружение готово и профиль обычный — иначе каждый тест ловил бы плашку.
  (convertHealth as jest.Mock).mockResolvedValue({ ready: true, items: [], problems: [] });
  (convertProfile as jest.Mock).mockResolvedValue({ profile: 'full', llm_default: true });
});

// Слив микрозадач. Цепочка промисов внутри эффекта разрешается вне реакции
// React, и без act её setState не применятся. Правило testing-library видит
// «пустой act» и ругается, но пустота здесь и есть смысл вызова.
// eslint-disable-next-line testing-library/no-unnecessary-act
const flush = () => act(async () => {});

afterEach(() => {
  // Возврат настоящих таймеров ОБЯЗАН быть здесь, а не в конце теста: упавший
  // тест до своей последней строки не доходит, и подставные таймеры утекают
  // в следующий — тот виснет на реальном ожидании и падает следом.
  jest.useRealTimers();
});

describe('ConvertScreen', () => {
  it('нативный PDF: вердикт классификации и «Пропустить» → старый путь анализа', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'native', confidence: 'high' });
    mockAnalyzeDocument.mockResolvedValue({ success: true, data: { fields: {} } });
    const onComplete = jest.fn();

    render(<ConvertScreen file={pdfFile} onComplete={onComplete} onBack={jest.fn()} />);

    expect(await screen.findByText(/текстовый слой/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Пропустить конвертацию/ }));

    await waitFor(() => expect(onComplete).toHaveBeenCalled());
    expect(mockAnalyzeDocument).toHaveBeenCalledWith(pdfFile);
    // Конвертер НЕ гасим: его убивает сторож простоя на бэкенде. Остановка отсюда
    // означала холодный старт с загрузкой LLM на каждом следующем заявлении.
    expect(mockStop).not.toHaveBeenCalled();
  });

  it('скан: конвертация с дефолт-флагами родного фронта, поллинг → текстовый предпросмотр', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'j1' });
    mockStatus
      .mockResolvedValueOnce({ job_id: 'j1', status: 'running', stage: 'OCR', progress: 0.4 })
      .mockResolvedValue({ job_id: 'j1', status: 'done', progress: 1 });
    mockDownload.mockResolvedValue(new Blob([new Uint8Array([80, 75])]));
    mockDocxText.mockResolvedValue({ success: true, text: 'Распознанный текст заявления' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));
    // КРИТИЧНО: флаги = дефолты родного фронта конвертера; без них API-дефолт
    // no_highlight=true отключал LLM-доочистку — качество падало (баг Андрея)
    expect(mockScan).toHaveBeenCalledWith(
      pdfFile,
      expect.objectContaining({ no_highlight: false, iim: true }),
      expect.any(String) // третий аргумент — ключ идемпотентности
    );

    // Поллинг каждые 1.5 с: ждём предпросмотра (running → done → download → текст)
    const editor = await screen.findByTestId('text-editor', {}, { timeout: 7000 });
    expect(editor).toHaveValue('Распознанный текст заявления');
    expect(screen.getByTestId('pdf-panel')).toBeInTheDocument();
    expect(mockDownload).toHaveBeenCalledWith('j1');
  }, 15000);

  it('правка текста и «Далее» → analyzeText с правленым текстом', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'j1' });
    mockStatus.mockResolvedValue({ job_id: 'j1', status: 'done', progress: 1 });
    mockDownload.mockResolvedValue(new Blob([new Uint8Array([80, 75])]));
    mockDocxText.mockResolvedValue({ success: true, text: 'Сумма 100' });
    mockAnalyzeText.mockResolvedValue({ success: true, data: { fields: {} } });
    const onComplete = jest.fn();

    render(<ConvertScreen file={pdfFile} onComplete={onComplete} onBack={jest.fn()} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));
    const editor = await screen.findByTestId('text-editor', {}, { timeout: 7000 });

    await userEvent.clear(editor);
    await userEvent.type(editor, 'Сумма 200');
    await userEvent.click(screen.getByRole('button', { name: 'Далее' }));

    await waitFor(() => expect(onComplete).toHaveBeenCalled());
    expect(mockAnalyzeText).toHaveBeenCalledWith('Сумма 200');
    expect(mockStop).not.toHaveBeenCalled(); // см. комментарий выше про сторож простоя
  }, 15000);

  it('ошибка конвертации → экран ошибки с «Повторить» и «Пропустить»', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'j2' });
    mockStatus.mockResolvedValue({ job_id: 'j2', status: 'error', error: 'OCR упал' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    expect(await screen.findByText('OCR упал', {}, { timeout: 7000 })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Пропустить конвертацию/ })).toBeInTheDocument();
  }, 15000);

  // ── Готовность окружения ──

  it('окружение не готово: плашка с причинами и кнопкой «Проверить снова»', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    (convertHealth as jest.Mock).mockResolvedValue({
      ready: false,
      problems: ['Нет русского языка Tesseract'],
      items: [
        { name: 'tesseract', critical: true, ok: false, detail: 'нет языка rus' },
        { name: 'LLM-модель (gguf)', critical: false, ok: false, detail: 'не найдена' },
        { name: 'свободный диск', critical: true, ok: true, detail: '218 ГБ' },
      ],
    });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);

    expect(await screen.findByText('Конвертер не готов к работе')).toBeInTheDocument();
    expect(screen.getByText('Нет русского языка Tesseract')).toBeInTheDocument();
    expect(screen.getByText(/tesseract: нет языка rus/)).toBeInTheDocument();
    // Некритичные и исправные строки в плашку не попадают — это не проблемы.
    expect(screen.queryByText(/LLM-модель/)).not.toBeInTheDocument();
    expect(screen.queryByText(/218 ГБ/)).not.toBeInTheDocument();
    // Конвертировать всё равно разрешаем: решать пользователю.
    expect(screen.getByRole('button', { name: 'Конвертировать' })).toBeInTheDocument();
  }, 15000);

  it('окружение готово: плашки нет', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await screen.findByRole('button', { name: 'Конвертировать' });

    expect(screen.queryByText('Конвертер не готов к работе')).not.toBeInTheDocument();
  }, 15000);

  it('«Проверить снова» перезапрашивает готовность', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    (convertHealth as jest.Mock)
      .mockResolvedValueOnce({ ready: false, problems: ['Нет языка rus'], items: [] })
      .mockResolvedValue({ ready: true, problems: [], items: [] });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await screen.findByText('Конвертер не готов к работе');

    await userEvent.click(screen.getByRole('button', { name: 'Проверить снова' }));

    await waitFor(() =>
      expect(screen.queryByText('Конвертер не готов к работе')).not.toBeInTheDocument()
    );
    expect(convertHealth).toHaveBeenCalledTimes(2);
  }, 15000);

  it('отказ /convert/health работу не блокирует', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    (convertHealth as jest.Mock).mockRejectedValue(new TypeError('Failed to fetch'));

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);

    expect(await screen.findByRole('button', { name: 'Конвертировать' })).toBeInTheDocument();
    expect(screen.queryByText(/Сервер конвертера не отвечает/)).not.toBeInTheDocument();
  }, 15000);

  // ── Профиль: дефолт доочистки ──

  it('llm_default: false — галочка доочистки снята, и флаг уходит выключенным', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    (convertProfile as jest.Mock).mockResolvedValue({ profile: 'lean', llm_default: false });
    mockScan.mockResolvedValue({ job_id: 'jd1' });
    mockStatus.mockResolvedValue({ job_id: 'jd1', status: 'running', progress: 0.1, stage: 'OCR' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    expect(await findFlagCheckbox(/Улучшать текст нейросетью/)).not.toBeChecked();

    await userEvent.click(screen.getByRole('button', { name: 'Конвертировать' }));
    expect(mockScan.mock.calls[0][1]).toMatchObject({ iim: false });
  }, 15000);

  it('llm_default: true — галочка стоит (дефолт родного фронта сохранён)', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);

    expect(await findFlagCheckbox(/Улучшать текст нейросетью/)).toBeChecked();
  }, 15000);

  // ── Профиль из настроек приложения ──

  it('выбранный в настройках режим уходит полем profile', async () => {
    // Сайдкар перезапускается сторожем простоя, поэтому выбор передаётся при
    // каждом запуске, а не хранится в его настройках.
    window.localStorage.setItem('sberact.converter.profile', 'lean');
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'jpr1' });
    mockStatus.mockResolvedValue({ job_id: 'jpr1', status: 'running', progress: 0.1, stage: 'OCR' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    expect(mockScan.mock.calls[0][1]).toMatchObject({ profile: 'lean' });
  }, 15000);

  it('«Автоматически» поле profile не шлёт — решает конвертер', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'jpr2' });
    mockStatus.mockResolvedValue({ job_id: 'jpr2', status: 'running', progress: 0.1, stage: 'OCR' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    expect(mockScan.mock.calls[0][1]).not.toHaveProperty('profile');
  }, 15000);

  it('выбор доочистки в настройках старше решения конвертера', async () => {
    // Конвертер на этой машине включил бы доочистку, но юрист выключил её.
    window.localStorage.setItem('sberact.converter.llmDefault', 'off');
    (convertProfile as jest.Mock).mockResolvedValue({ profile: 'full', llm_default: true });
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);

    expect(await findFlagCheckbox(/Улучшать текст нейросетью/)).not.toBeChecked();
  }, 15000);

  // ── Предупреждения сервера ──

  it('warning из ответа scan показывается, но работу не прерывает', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({
      job_id: 'jw1',
      warning: 'В файле есть текстовый слой — возможно, подойдёт нативный режим.',
    });
    mockStatus.mockResolvedValue({ job_id: 'jw1', status: 'running', progress: 0.2, stage: 'OCR' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    expect(await screen.findByText(/есть текстовый слой/)).toBeInTheDocument();
    expect(screen.getByText('Конвертируем документ…')).toBeInTheDocument();
  }, 15000);

  it('warning из статуса задачи тоже доходит', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'jw2' });
    mockStatus.mockResolvedValue({
      job_id: 'jw2',
      status: 'running',
      progress: 0.5,
      stage: 'OCR',
      warning: 'Мало свободной памяти под этот файл.',
    });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    expect(
      await screen.findByText('Мало свободной памяти под этот файл.', {}, { timeout: 7000 })
    ).toBeInTheDocument();
  }, 15000);

  // ── Доочистка по кнопке ──

  // Подводит задачу к предпросмотру: скан готов, доочистка ещё не прогонялась.
  const renderPolishable = async (over?: Record<string, unknown>) => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'jpo1' });
    mockStatus.mockResolvedValue({
      job_id: 'jpo1',
      status: 'done',
      progress: 1,
      mode: 'scan',
      polished: false,
      ...over,
    });
    mockDownload.mockResolvedValue(new Blob(['docx']));
    mockDocxText.mockResolvedValue({ text: 'Распознанный текст', sections: [] });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));
    await screen.findByTestId('text-editor', {}, { timeout: 7000 });
  };

  it('«Доочистить текст»: текст заменяется результатом, кнопка уходит', async () => {
    await renderPolishable();
    (convertPolish as jest.Mock).mockResolvedValue({ job_id: 'jpo1', status: 'queued' });
    mockStatus.mockResolvedValue({
      job_id: 'jpo1',
      status: 'done',
      progress: 1,
      mode: 'scan',
      polished: true,
      stage: 'Доочистка: исправлено 7',
    });
    mockDocxText.mockResolvedValue({ text: 'Доочищенный текст', sections: [] });

    await userEvent.click(screen.getByRole('button', { name: 'Доочистить текст' }));

    expect(await screen.findByText('Доочистка: исправлено 7', {}, { timeout: 7000 })).toBeInTheDocument();
    expect(screen.getByTestId('text-editor')).toHaveValue('Доочищенный текст');
    expect(convertPolish).toHaveBeenCalledWith('jpo1');
    // Второй раз доочищать нечего.
    expect(screen.queryByRole('button', { name: 'Доочистить текст' })).not.toBeInTheDocument();
  }, 20000);

  it('кнопки нет у нативного режима и у уже доочищенного документа', async () => {
    await renderPolishable({ mode: 'native' });
    expect(screen.queryByRole('button', { name: 'Доочистить текст' })).not.toBeInTheDocument();

    cleanup();
    await renderPolishable({ polished: true });
    expect(screen.queryByRole('button', { name: 'Доочистить текст' })).not.toBeInTheDocument();
  }, 20000);

  it('правки в тексте: спрашиваем до перезаписи', async () => {
    await renderPolishable();
    (convertPolish as jest.Mock).mockResolvedValue({ job_id: 'jpo1', status: 'queued' });

    const editor = screen.getByTestId('text-editor');
    await userEvent.clear(editor);
    await userEvent.type(editor, 'Моя правка');

    await userEvent.click(screen.getByRole('button', { name: 'Доочистить текст' }));

    expect(await screen.findByText('Доочистить текст?')).toBeInTheDocument();
    expect(convertPolish).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(convertPolish).not.toHaveBeenCalled();
    expect(screen.getByTestId('text-editor')).toHaveValue('Моя правка');
  }, 20000);

  it('без правок спрашивать не о чем — доочистка идёт сразу', async () => {
    await renderPolishable();
    (convertPolish as jest.Mock).mockResolvedValue({ job_id: 'jpo1', status: 'queued' });
    mockStatus.mockResolvedValue({ job_id: 'jpo1', status: 'done', mode: 'scan', polished: true, stage: 'Готово' });

    await userEvent.click(screen.getByRole('button', { name: 'Доочистить текст' }));

    await waitFor(() => expect(convertPolish).toHaveBeenCalledWith('jpo1'));
    expect(screen.queryByText('Доочистить текст?')).not.toBeInTheDocument();
  }, 20000);

  it('доочистка сломалась: документ цел, это предупреждение, а не ошибка', async () => {
    await renderPolishable();
    (convertPolish as jest.Mock).mockResolvedValue({ job_id: 'jpo1', status: 'queued' });
    // Конвертер оставляет задачу в done: сломалась доочистка, не результат.
    mockStatus.mockResolvedValue({
      job_id: 'jpo1',
      status: 'done',
      mode: 'scan',
      polished: false,
      stage: 'Доочистка не удалась',
      error: 'Доочистка не загрузилась.',
      error_code: 'LLM_UNAVAILABLE',
    });

    await userEvent.click(screen.getByRole('button', { name: 'Доочистить текст' }));

    expect(await screen.findByText('Доочистка не загрузилась.', {}, { timeout: 7000 })).toBeInTheDocument();
    // Остаёмся в предпросмотре, экрана ошибки нет.
    expect(screen.getByTestId('text-editor')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Повторить' })).not.toBeInTheDocument();
  }, 20000);

  it('отказ запуска доочистки (409) показывается плашкой', async () => {
    await renderPolishable();
    (convertPolish as jest.Mock).mockRejectedValue(
      new Error('HTTP 409: {"detail": "Этот документ уже доочищен."}')
    );

    await userEvent.click(screen.getByRole('button', { name: 'Доочистить текст' }));

    expect(await screen.findByText('Этот документ уже доочищен.')).toBeInTheDocument();
    expect(screen.getByTestId('text-editor')).toHaveValue('Распознанный текст');
  }, 20000);

  // ── Отмена задачи ──

  it('отмена из очереди (200 cancelled): возврат к выбору режима с пометкой', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'jc1' });
    mockStatus.mockResolvedValue({ job_id: 'jc1', status: 'running', progress: 0.2, stage: 'OCR' });
    (convertCancel as jest.Mock).mockResolvedValue({ job_id: 'jc1', state: 'cancelled' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    await userEvent.click(await screen.findByRole('button', { name: 'Отменить' }));

    expect(await screen.findByText('Конвертация отменена.')).toBeInTheDocument();
    expect(convertCancel).toHaveBeenCalledWith('jc1');
    // Экран ошибки не показываем: отмена — не сбой.
    expect(screen.queryByRole('button', { name: 'Повторить' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Конвертировать' })).toBeInTheDocument();
  }, 15000);

  it('отмена на ходу (202): кнопка ждёт, итог приходит опросом с кодом CANCELLED', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'jc2' });
    mockStatus
      .mockResolvedValueOnce({ job_id: 'jc2', status: 'running', progress: 0.3, stage: 'OCR' })
      .mockResolvedValue({
        job_id: 'jc2',
        status: 'error',
        error: 'Отменено пользователем',
        error_code: 'CANCELLED',
      });
    (convertCancel as jest.Mock).mockResolvedValue({ job_id: 'jc2', state: 'cancelling' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Отменить' }));

    expect(await screen.findByRole('button', { name: 'Останавливаем…' })).toBeInTheDocument();
    expect(await screen.findByText('Конвертация отменена.', {}, { timeout: 7000 })).toBeInTheDocument();
    expect(screen.queryByText('Отменено пользователем')).not.toBeInTheDocument();
  }, 15000);

  it('прервать нечем (409): предупреждение, работа продолжается', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'native' });
    (convertNative as jest.Mock).mockResolvedValue({ job_id: 'jc3' });
    mockStatus.mockResolvedValue({ job_id: 'jc3', status: 'running', progress: 0.4, stage: 'pdf2docx' });
    (convertCancel as jest.Mock).mockRejectedValue(
      new Error('HTTP 409: {"detail": "Эту работу нельзя прервать на ходу: нативный режим идёт внутри pdf2docx."}')
    );

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Отменить' }));

    expect(await screen.findByText(/нельзя прервать на ходу/)).toBeInTheDocument();
    // Это предупреждение, а не экран ошибки: прогресс остаётся на месте.
    expect(screen.getByText('Конвертируем документ…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Отменить' })).toBeInTheDocument();
  }, 15000);

  // ── Лог задачи ──

  it('«Подробнее» показывает лог задачи', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'jl1' });
    mockStatus.mockResolvedValue({
      job_id: 'jl1',
      status: 'error',
      error: 'Не хватило памяти.',
      error_code: 'OUT_OF_MEMORY',
      error_hint: 'Закройте другие программы и попробуйте снова.',
    });
    (convertLog as jest.Mock).mockResolvedValue({ job_id: 'jl1', text: '12:04:31 ocr: страница 3/14' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    // Причина и подсказка из статуса задачи — обе на экране.
    expect(await screen.findByText('Не хватило памяти.', {}, { timeout: 7000 })).toBeInTheDocument();
    expect(screen.getByText('Закройте другие программы и попробуйте снова.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Подробнее' }));
    expect(await screen.findByTestId('job-log')).toHaveTextContent('ocr: страница 3/14');
    expect(convertLog).toHaveBeenCalledWith('jl1', 16384);
  }, 15000);

  it('INTERRUPTED объясняется перезапуском, если сервер не дал подсказки', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'jl2' });
    mockStatus.mockResolvedValue({
      job_id: 'jl2',
      status: 'error',
      error: 'Работа прервана.',
      error_code: 'INTERRUPTED',
    });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    expect(await screen.findByText('Работа прервана.', {}, { timeout: 7000 })).toBeInTheDocument();
    expect(screen.getByText(/перезапускался во время работы/)).toBeInTheDocument();
  }, 15000);

  // ── Терпимость опроса к обрывам ──

  it('обрыв опроса не роняет задачу: следующий тик забирает результат', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'jp1' });
    mockStatus
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValue({ job_id: 'jp1', status: 'done', progress: 1 });
    mockDownload.mockResolvedValue(new Blob(['docx']));
    mockDocxText.mockResolvedValue({ text: 'Текст после обрывов', sections: [] });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    expect(
      await screen.findByTestId('text-editor', {}, { timeout: 12000 })
    ).toHaveValue('Текст после обрывов');
    expect(screen.queryByText(/Сервер конвертера не отвечает/)).not.toBeInTheDocument();
  }, 20000);

  it('404 на опросе не терпим: задачи нет — сразу ошибка', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'jp2' });
    mockStatus.mockRejectedValue(new Error('HTTP 404: {"detail": "Задача не найдена."}'));

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    expect(await screen.findByText('Задача не найдена.', {}, { timeout: 7000 })).toBeInTheDocument();
    // Ровно одна попытка: повторять нечего.
    expect(mockStatus).toHaveBeenCalledTimes(1);
  }, 15000);

  // Ключ идемпотентности: одно нажатие — один ключ, повтор после ошибки — новый.
  it('«Конвертировать» шлёт ключ задачи, «Повторить» — уже другой', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'j9' });
    mockStatus.mockResolvedValue({ job_id: 'j9', status: 'error', error: 'OCR упал' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));
    await screen.findByText('OCR упал', {}, { timeout: 7000 });

    const firstKey = mockScan.mock.calls[0][2];
    expect(typeof firstKey).toBe('string');
    expect(firstKey).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    await waitFor(() => expect(mockScan).toHaveBeenCalledTimes(2));
    expect(mockScan.mock.calls[1][2]).toBeTruthy();
    expect(mockScan.mock.calls[1][2]).not.toBe(firstKey);
  }, 15000);

  it('нативный режим тоже идёт с ключом', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'native' });
    const mockNative = convertNative as jest.Mock;
    mockNative.mockResolvedValue({ job_id: 'n1' });
    mockStatus.mockResolvedValue({ job_id: 'n1', status: 'running', progress: 0.1, stage: 'Идём' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    await waitFor(() => expect(mockNative).toHaveBeenCalled());
    expect(mockNative.mock.calls[0][1]).toBeTruthy();
  }, 15000);

  // Отказ конвертера приходит структурным detail, а preload кладёт тело прямо
  // в текст ошибки. Юрист должен увидеть причину и что делать, а не «HTTP 400».
  it('структурный отказ: показываются причина и подсказка, а не HTTP-строка', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockRejectedValue(
      new Error(
        'HTTP 400: ' +
          JSON.stringify({
            detail: {
              code: 'PDF_ENCRYPTED',
              message: 'PDF защищён паролем.',
              hint: 'Снимите пароль в любой программе для работы с PDF и попробуйте снова.',
            },
          })
      )
    );

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    expect(await screen.findByText('PDF защищён паролем.', {}, { timeout: 7000 })).toBeInTheDocument();
    expect(
      screen.getByText(/Снимите пароль в любой программе для работы с PDF/)
    ).toBeInTheDocument();
    expect(screen.queryByText(/HTTP 400/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
  }, 15000);

  it('конвертер не отвечает на запуске: вместо «Failed to fetch» — внятный текст', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockRejectedValue(new TypeError('Failed to fetch'));

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));

    expect(
      await screen.findByText(/Сервер конвертера не отвечает/, {}, { timeout: 7000 })
    ).toBeInTheDocument();
    expect(screen.queryByText(/Failed to fetch/)).not.toBeInTheDocument();
  }, 15000);

  it('терпение опроса не бесконечно: после шести обрывов — ошибка', async () => {
    // Настоящими таймерами тест ждал бы ~48 секунд (пауза растёт), поэтому
    // крутим подставные. Порядок как в тесте выше: сперва слить микрозадачи,
    // чтобы тик успел встать в очередь, и только потом двигать время.
    jest.useFakeTimers();
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'jp3' });
    mockStatus.mockRejectedValue(new TypeError('Failed to fetch'));

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await flush();
    fireEvent.click(screen.getByRole('button', { name: 'Конвертировать' }));

    for (let attempt = 0; attempt <= 6; attempt++) {
      // eslint-disable-next-line no-await-in-loop
      await flush();
      jest.advanceTimersByTime(60000);
    }
    await flush();

    expect(screen.getByText(/Сервер конвертера не отвечает/)).toBeInTheDocument();
    expect(mockStatus).toHaveBeenCalledTimes(6);
  }, 20000);

  it('конвертер не поднялся → ошибка со скип-фолбэком', async () => {
    // Экран НЕ показывает ошибку с первой неудачи: холодный старт конвертера
    // занимает до минуты, поэтому запуск тихо повторяется 5 раз с паузой 3 с,
    // и сообщение появляется только через ~15 секунд. Настоящими таймерами тест
    // столько бы и висел — прокручиваем их подставными.
    jest.useFakeTimers();
    mockStart.mockResolvedValue({ ok: false, error: 'Конвертер не установлен' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);

    // Jest 27 (CRA 5) не умеет advanceTimersByTimeAsync, поэтому крутим паузы
    // вручную. Порядок важен: сперва слить микрозадачи, чтобы промис
    // converterStart разрешился и пауза успела встать в очередь таймеров, и
    // только потом двигать время. Наоборот — первый сдвиг уходит вхолостую.
    for (let attempt = 0; attempt < 5; attempt++) {
      // eslint-disable-next-line no-await-in-loop
      await flush();
      // eslint-disable-next-line no-await-in-loop
      await act(async () => {
        jest.advanceTimersByTime(3000);
      });
    }
    await flush();

    expect(screen.getByText('Конвертер не установлен')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Пропустить конвертацию/ })).toBeInTheDocument();
    expect(mockAnalyze).not.toHaveBeenCalled();
    // Пять попыток — ровно столько, сколько заложено в экране: меньше значит
    // ретрай сломан, больше — пользователь ждёт ошибку дольше нужного.
    expect(mockStart).toHaveBeenCalledTimes(5);
  });

  // Поллинг: подставные таймеры + ручное разрешение промиса статуса. Настоящими
  // таймерами эти сценарии не воспроизвести — нужен статус, который «думает»
  // дольше интервала опроса.
  const bootToReady = async () => {
    // boot(): converterStart → convertAnalyze → phase 'ready'. Цепочка промисов,
    // поэтому сливаем микрозадачи дважды.
    await flush();
    await flush();
  };

  it('медленный статус: тик поллинга не наслаивается на предыдущий', async () => {
    // Регрессия: setInterval не ждёт предыдущий async-колбэк. Под OCR-нагрузкой
    // /convert/status отвечает дольше 1.5 с, и два тика видели done — документ
    // скачивался и разбирался дважды.
    jest.useFakeTimers();
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'j9' });
    let releaseStatus: (v: unknown) => void = () => {};
    mockStatus.mockImplementation(
      () => new Promise((resolve) => { releaseStatus = resolve; })
    );
    mockDownload.mockResolvedValue(new Blob([new Uint8Array([80, 75])]));
    mockDocxText.mockResolvedValue({ success: true, text: 'Распознанный текст' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);
    await bootToReady();
    fireEvent.click(screen.getByRole('button', { name: 'Конвертировать' }));
    await flush(); // convertScan → setInterval

    await act(async () => { jest.advanceTimersByTime(1500); }); // тик 1 ушёл
    await act(async () => { jest.advanceTimersByTime(3000); }); // ещё два интервала
    // Ответа на первый опрос ещё нет — новых опросов быть не должно.
    expect(mockStatus).toHaveBeenCalledTimes(1);

    await act(async () => { releaseStatus({ job_id: 'j9', status: 'done', progress: 1 }); });
    await flush();
    expect(mockDownload).toHaveBeenCalledTimes(1);
    expect(mockDocxText).toHaveBeenCalledTimes(1);
  });

  it('смена файла гасит поллинг: чужой текст в предпросмотр не попадает', async () => {
    // Регрессия: cleanup висел только на размонтировании. Юрист возвращался на
    // загрузку и приносил другой PDF, а таймер первой задачи дописывал в
    // состояние текст ПРЕДЫДУЩЕГО документа.
    jest.useFakeTimers();
    mockAnalyze.mockResolvedValue({ suggested: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'старый' });
    let releaseStatus: (v: unknown) => void = () => {};
    mockStatus.mockImplementation(
      () => new Promise((resolve) => { releaseStatus = resolve; })
    );
    mockDownload.mockResolvedValue(new Blob([new Uint8Array([80, 75])]));
    mockDocxText.mockResolvedValue({ success: true, text: 'ТЕКСТ ЧУЖОГО ДОКУМЕНТА' });

    const { rerender } = render(
      <ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />
    );
    await bootToReady();
    fireEvent.click(screen.getByRole('button', { name: 'Конвертировать' }));
    await flush();
    await act(async () => { jest.advanceTimersByTime(1500); });
    expect(mockStatus).toHaveBeenCalledTimes(1);

    const otherPdf = new File([new Uint8Array([9])], 'другой.pdf', { type: 'application/pdf' });
    rerender(<ConvertScreen file={otherPdf} onComplete={jest.fn()} onBack={jest.fn()} />);
    await bootToReady();

    // Старая задача досчиталась уже ПОСЛЕ смены файла
    await act(async () => { releaseStatus({ job_id: 'старый', status: 'done', progress: 1 }); });
    await flush();

    expect(mockDownload).not.toHaveBeenCalled();
    expect(screen.queryByTestId('text-editor')).not.toBeInTheDocument();
    // И таймер мёртв: старую задачу больше не опрашиваем
    await act(async () => { jest.advanceTimersByTime(6000); });
    expect(mockStatus).toHaveBeenCalledTimes(1);
  });

  it('«Назад» НЕ останавливает конвертер — им распоряжается сторож простоя', async () => {
    mockAnalyze.mockResolvedValue({ suggested: 'native' });
    const onBack = jest.fn();

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={onBack} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Назад' }));
    expect(onBack).toHaveBeenCalled();
    // Раньше UI гасил sidecar на каждом уходе с шага, и следующий PDF платил
    // холодным стартом с загрузкой LLM. Теперь память возвращает сторож простоя
    // на бэкенде (CONVERTER_IDLE_TIMEOUT_S), а UI в это не лезет.
    expect(mockStop).not.toHaveBeenCalled();
  });
});
