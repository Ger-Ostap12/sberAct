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
}));

// Тяжёлые панели предпросмотра (pdfjs/mammoth) в юнит-тестах не рендерим
jest.mock('../PdfPanel', () => () => <div data-testid="pdf-panel" />);
jest.mock('../DocxPreviewEditor', () => {
  const { forwardRef } = jest.requireActual('react');
  const MockEditor = forwardRef((_props: unknown, _ref: unknown) => (
    <div data-testid="docx-editor-mock" />
  ));
  return { __esModule: true, default: MockEditor };
});

import {
  analyzeDocument,
  convertAnalyze,
  convertDownload,
  convertScan,
  convertStatus,
  converterStart,
  converterStop,
} from '../../../services/electronApi';

const mockStart = converterStart as jest.Mock;
const mockAnalyze = convertAnalyze as jest.Mock;
const mockScan = convertScan as jest.Mock;
const mockStatus = convertStatus as jest.Mock;
const mockDownload = convertDownload as jest.Mock;
const mockAnalyzeDocument = analyzeDocument as jest.Mock;
const mockStop = converterStop as jest.Mock;

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
    mockAnalyze.mockResolvedValue({ mode: 'native' });
    mockAnalyzeDocument.mockResolvedValue({ success: true, data: { fields: {} } });
    const onComplete = jest.fn();

    render(<ConvertScreen file={pdfFile} onComplete={onComplete} onBack={jest.fn()} />);

    expect(await screen.findByText(/текстовый слой/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Пропустить конвертацию/ }));

    await waitFor(() => expect(onComplete).toHaveBeenCalled());
    expect(mockAnalyzeDocument).toHaveBeenCalledWith(pdfFile);
    expect(mockStop).toHaveBeenCalled();
  });

  it('скан: конвертация с поллингом до done → предпросмотр', async () => {
    mockAnalyze.mockResolvedValue({ mode: 'scan' });
    mockScan.mockResolvedValue({ job_id: 'j1' });
    mockStatus
      .mockResolvedValueOnce({ job_id: 'j1', status: 'running', stage: 'OCR', progress: 0.4 })
      .mockResolvedValue({ job_id: 'j1', status: 'done', progress: 1 });
    mockDownload.mockResolvedValue(new Blob([new Uint8Array([80, 75])]));

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={jest.fn()} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Конвертировать' }));
    expect(mockScan).toHaveBeenCalledWith(pdfFile);

    // Поллинг каждые 1.5 с: ждём предпросмотра (running → done → download)
    expect(await screen.findByTestId('docx-editor-mock', {}, { timeout: 7000 })).toBeInTheDocument();
    expect(screen.getByTestId('pdf-panel')).toBeInTheDocument();
    expect(mockDownload).toHaveBeenCalledWith('j1');
  }, 15000);

  it('ошибка конвертации → экран ошибки с «Повторить» и «Пропустить»', async () => {
    mockAnalyze.mockResolvedValue({ mode: 'scan' });
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

  it('«Назад» останавливает конвертер', async () => {
    mockAnalyze.mockResolvedValue({ mode: 'native' });
    const onBack = jest.fn();

    render(<ConvertScreen file={pdfFile} onComplete={jest.fn()} onBack={onBack} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Назад' }));
    expect(onBack).toHaveBeenCalled();
    expect(mockStop).toHaveBeenCalled();
  });
});
