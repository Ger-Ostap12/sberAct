import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
