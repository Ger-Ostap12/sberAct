import React from 'react';
import { render, screen } from '@testing-library/react';
import DebtorNameWarning from '../DebtorNameWarning';

describe('DebtorNameWarning', () => {
  const warning = {
    regexName: 'Форте Пром ГМБХ',
    semanticName: 'ООО «Форте Пром ГМБХ»',
    message: 'Имя должника, найденное вторым способом проверки, отличается от определённого автоматически.',
  };

  it('не рендерится без предупреждения (regex и семантика совпали)', () => {
    const { container } = render(<DebtorNameWarning />);
    expect(container).toBeEmptyDOMElement();
  });

  it('не рендерится при warning=null', () => {
    const { container } = render(<DebtorNameWarning warning={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('показывает оба имени при расхождении', () => {
    render(<DebtorNameWarning warning={warning} />);
    expect(screen.getByText(/Перепроверьте имя должника/)).toBeInTheDocument();
    expect(screen.getByText(/Форте Пром ГМБХ/)).toBeInTheDocument();
    expect(screen.getByText(/ООО «Форте Пром ГМБХ»/)).toBeInTheDocument();
  });
});
