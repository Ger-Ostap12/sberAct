import React from 'react';
import { render, screen } from '@testing-library/react';
import EntityTypeWarning from '../EntityTypeWarning';

describe('EntityTypeWarning', () => {
  const warning = {
    documentType: 'initiation_legal',
    expectedEntityType: 'legal' as const,
    actualEntityType: 'individual',
    message: 'Тип документа предполагает тип лица должника, отличный от определённого по реквизитам.',
  };

  it('не рендерится без предупреждения (согласие regex и реквизитов)', () => {
    const { container } = render(<EntityTypeWarning />);
    expect(container).toBeEmptyDOMElement();
  });

  it('не рендерится при warning=null', () => {
    const { container } = render(<EntityTypeWarning warning={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('показывает человекочитаемые названия обоих типов лица', () => {
    render(<EntityTypeWarning warning={warning} />);
    expect(screen.getByText(/Перепроверьте тип лица должника/)).toBeInTheDocument();
    expect(screen.getByText(/юридическое лицо/)).toBeInTheDocument();
    expect(screen.getByText(/физическое лицо/)).toBeInTheDocument();
  });

  it('неизвестный ключ типа лица показывается как есть, не ломает рендер', () => {
    render(<EntityTypeWarning warning={{ ...warning, actualEntityType: 'kfh' }} />);
    expect(screen.getByText(/kfh/)).toBeInTheDocument();
  });
});
