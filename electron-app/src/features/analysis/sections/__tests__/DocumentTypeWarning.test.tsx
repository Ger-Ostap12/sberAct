import React from 'react';
import { render, screen } from '@testing-library/react';
import DocumentTypeWarning from '../DocumentTypeWarning';

describe('DocumentTypeWarning', () => {
  const warning = {
    documentType: 'initiation_physical',
    regexFamily: 'initiation' as const,
    semanticFamily: 'rtk' as const,
    message: 'Автоматическое определение типа документа не подтверждено вторым способом проверки.',
  };

  it('не рендерится без предупреждения (согласие regex и семантики)', () => {
    const { container } = render(<DocumentTypeWarning />);
    expect(container).toBeEmptyDOMElement();
  });

  it('не рендерится при warning=null', () => {
    const { container } = render(<DocumentTypeWarning warning={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('показывает обе версии семейства при расхождении', () => {
    render(<DocumentTypeWarning warning={warning} />);
    expect(screen.getByText(/Перепроверьте тип заявления/)).toBeInTheDocument();
    expect(screen.getByText(/инициирование/)).toBeInTheDocument();
    expect(screen.getByText(/включение в реестр требований кредиторов/)).toBeInTheDocument();
  });
});
