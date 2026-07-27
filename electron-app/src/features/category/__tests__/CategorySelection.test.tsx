import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import CategorySelection from '../CategorySelection';
import { ExtractedData } from '../../../types';

const makeData = (documentType: string): ExtractedData => ({
  documentType,
  confidence: 1,
  fields: {},
  rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

describe('CategorySelection', () => {
  it('рендерит три категории', () => {
    render(<CategorySelection onSelect={() => {}} onBack={() => {}} />);
    expect(screen.getByText('Банкротство')).toBeInTheDocument();
    expect(screen.getByText('Взыскание')).toBeInTheDocument();
    expect(screen.getByText('Ипотека')).toBeInTheDocument();
  });

  // Чип «Рекомендуется» — сосед CardActionArea внутри той же Card. Проверяем, что
  // он в одной карточке с ожидаемым заголовком (общий предок .MuiCard-root).
  const recommendedTitle = () => {
    const chip = screen.getByText('Рекомендуется');
    const card = chip.closest('.MuiCard-root') as HTMLElement;
    return card.querySelector('h6')?.textContent;
  };

  it('рекомендует «Ипотека» для mortgage_claim', () => {
    render(
      <CategorySelection extractedData={makeData('mortgage_claim')} onSelect={() => {}} onBack={() => {}} />,
    );
    expect(recommendedTitle()).toBe('Ипотека');
  });

  it('рекомендует «Банкротство» по умолчанию (rtk_application)', () => {
    render(
      <CategorySelection extractedData={makeData('rtk_application')} onSelect={() => {}} onBack={() => {}} />,
    );
    expect(recommendedTitle()).toBe('Банкротство');
  });

  it('клик по категории вызывает onSelect с ключом', () => {
    const onSelect = jest.fn();
    render(<CategorySelection onSelect={onSelect} onBack={() => {}} />);
    fireEvent.click(screen.getByLabelText('Выбрать: Ипотека'));
    expect(onSelect).toHaveBeenCalledWith('mortgage');
  });

  it('кнопка «Назад» вызывает onBack', () => {
    const onBack = jest.fn();
    render(<CategorySelection onSelect={() => {}} onBack={onBack} />);
    fireEvent.click(screen.getByRole('button', { name: 'Назад' }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
