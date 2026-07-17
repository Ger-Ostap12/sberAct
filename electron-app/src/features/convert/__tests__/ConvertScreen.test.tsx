import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConvertScreen from '../ConvertScreen';

// Транспорт — моками: конвертер в тестах не поднимаем
jest.mock('../../../services/electronApi', () => ({
  analyzeDocument: jest.fn(),
  analyzeText: jest.fn(),
  convertAnalyze: jest.fn(),
  convertDownload: jest.fn(),
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
  convertDownload,
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

beforeEach(() => {
  jest.clearAllMocks();
  mockStart.mockResolvedValue({ ok: true });
  mockStop.mockResolvedValue({ ok: true });
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
      expect.objectContaining({ no_highlight: false, iim: true })
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

  it('конвертер не поднялся → ошибка со скип-фолбэком', async () => {
    mockStart.mockResolvedValue({ ok: false, error: 'Конвертер не установлен' });

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);

    expect(await screen.findByText('Конвертер не установлен')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Пропустить конвертацию/ })).toBeInTheDocument();
    expect(mockAnalyze).not.toHaveBeenCalled();
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
