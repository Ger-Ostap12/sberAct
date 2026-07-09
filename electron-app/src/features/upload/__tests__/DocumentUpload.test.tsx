import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DocumentUpload from '../DocumentUpload';

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
