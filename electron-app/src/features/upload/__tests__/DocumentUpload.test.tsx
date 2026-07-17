import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import DocumentUpload from '../DocumentUpload';
import { analyzeDocument, converterStart } from '../../../services/electronApi';

jest.mock('../../../services/electronApi', () => ({
  analyzeDocument: jest.fn(),
  converterStart: jest.fn(),
  selectFile: jest.fn(),
  hasElectronAPI: () => false,
  getElectronAPI: jest.fn(),
}));

// Кнопка «Выбрать файл»: в браузере нет моста Electron (selectFile всегда null),
// поэтому она должна открывать системный выбор через input дропзоны — раньше
// молча ничего не делала («не кликабельная», багрепорт Андрея).

describe('DocumentUpload — кнопка «Выбрать файл»', () => {
  it('в браузерном режиме клик открывает file input дропзоны', () => {
    const clickSpy = jest
      .spyOn(HTMLInputElement.prototype, 'click')
      .mockImplementation(() => {});
    render(<DocumentUpload onDocumentUploaded={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: 'Выбрать файл' }));
    expect(clickSpy).toHaveBeenCalled();
    clickSpy.mockRestore();
  });

  it('кнопка активна и подписана', () => {
    render(<DocumentUpload onDocumentUploaded={() => {}} />);
    expect(screen.getByRole('button', { name: 'Выбрать файл' })).toBeEnabled();
  });
});

describe('DocumentUpload — маршрутизация PDF на convert-шаг', () => {
  function dropFile(container: HTMLElement, file: File) {
    // Файл через input дропзоны (штатный onDrop-путь react-dropzone)
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
  }

  beforeEach(() => {
    jest.clearAllMocks();
    // CRA resetMocks сбрасывает реализации между тестами — задаём здесь
    (converterStart as jest.Mock).mockResolvedValue({ ok: true });
  });

  it('.pdf уходит в onPdfSelected БЕЗ прогрева конвертера, анализ не вызывается', async () => {
    const onPdfSelected = jest.fn();
    const { container } = render(
      <DocumentUpload onDocumentUploaded={() => {}} onPdfSelected={onPdfSelected} />
    );

    const pdf = new File([new Uint8Array([1])], 'скан.pdf', { type: 'application/pdf' });
    dropFile(container, pdf);

    await waitFor(() => expect(onPdfSelected).toHaveBeenCalled());
    expect((onPdfSelected as jest.Mock).mock.calls[0][0].name).toBe('скан.pdf');
    // Прогрев убран: старт конвертера — забота ConvertScreen. Дублирующий вызов
    // отсюда плодил гонку на бэкенде и глушил ошибку старта.
    expect(converterStart).not.toHaveBeenCalled();
    expect(analyzeDocument).not.toHaveBeenCalled();
  });

  it('.docx идёт прежним путём анализа даже при переданном onPdfSelected', async () => {
    (analyzeDocument as jest.Mock).mockResolvedValue({ success: true, data: {} });
    const onPdfSelected = jest.fn();
    const onDocumentUploaded = jest.fn();
    const { container } = render(
      <DocumentUpload onDocumentUploaded={onDocumentUploaded} onPdfSelected={onPdfSelected} />
    );

    const docx = new File([new Uint8Array([80, 75])], 'заявление.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });
    dropFile(container, docx);

    await waitFor(() => expect(onDocumentUploaded).toHaveBeenCalled());
    expect(analyzeDocument).toHaveBeenCalled();
    expect(onPdfSelected).not.toHaveBeenCalled();
  });
});
