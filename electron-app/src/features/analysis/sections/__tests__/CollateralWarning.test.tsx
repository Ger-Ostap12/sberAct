import React from 'react';
import { render, screen } from '@testing-library/react';
import CollateralWarning from '../CollateralWarning';

describe('CollateralWarning', () => {
  const warning = {
    documentType: 'legal_collection_collateral',
    expectedCollateral: true,
    actualCollateral: false,
    message: 'Тип документа предполагает наличие залога, но по извлечённым данным залог не найден.',
  };

  it('не рендерится без предупреждения (согласие regex и извлечённых данных)', () => {
    const { container } = render(<CollateralWarning />);
    expect(container).toBeEmptyDOMElement();
  });

  it('не рендерится при warning=null', () => {
    const { container } = render(<CollateralWarning warning={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('показывает несовпадение «ожидался залог, но не найден»', () => {
    render(<CollateralWarning warning={warning} />);
    expect(screen.getByText(/Перепроверьте наличие залога/)).toBeInTheDocument();
    expect(screen.getByText(/предполагает наличие залога/)).toBeInTheDocument();
    expect(screen.getByText(/залог не найден/)).toBeInTheDocument();
  });

  it('показывает несовпадение «залог не ожидался, но найден»', () => {
    render(<CollateralWarning warning={{ ...warning, expectedCollateral: false, actualCollateral: true }} />);
    expect(screen.getByText(/отсутствие залога/)).toBeInTheDocument();
    expect(screen.getByText(/залог обнаружен/)).toBeInTheDocument();
  });
});
