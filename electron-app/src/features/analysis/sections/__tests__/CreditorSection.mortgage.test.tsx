import React from 'react';
import { render, screen } from '@testing-library/react';
import CreditorSection from '../CreditorSection';

const noop = () => {};

describe('CreditorSection — режим ипотеки (Истец)', () => {
  it('банкротство: «Информация о кредиторе»', () => {
    render(
      <CreditorSection editedFields={{}} onFieldChange={noop} onCreditorChange={noop} banks={[]} />,
    );
    expect(screen.getByText('Информация о кредиторе')).toBeInTheDocument();
    expect(screen.getByText('Кредитор:')).toBeInTheDocument();
  });

  it('ипотека: «Информация об истце» и подписи «истца»', () => {
    render(
      <CreditorSection editedFields={{}} onFieldChange={noop} onCreditorChange={noop} banks={[]} mode="mortgage" />,
    );
    expect(screen.getByText('Информация об истце')).toBeInTheDocument();
    expect(screen.getByText('Истец:')).toBeInTheDocument();
    expect(screen.getByText('Юридический адрес истца:')).toBeInTheDocument();
    expect(screen.getByText('ОГРН истца:')).toBeInTheDocument();
    expect(screen.getByText('ИНН истца:')).toBeInTheDocument();
  });
});
