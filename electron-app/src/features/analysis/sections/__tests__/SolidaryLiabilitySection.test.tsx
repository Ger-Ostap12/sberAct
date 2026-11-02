import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import SolidaryLiabilitySection from '../SolidaryLiabilitySection';

it('требует явного выбора и не считает пустое значение несолидарным', () => {
  render(<SolidaryLiabilitySection editedFields={{}} onFieldChange={() => {}} />);
  expect(screen.getByRole('radio', { name: 'Солидарное' })).not.toBeChecked();
  expect(screen.getByRole('radio', { name: 'Несолидарное' })).not.toBeChecked();
});

it.each([['true', 'Солидарное'], ['false', 'Несолидарное']])('показывает выбор %s', (value, label) => {
  render(<SolidaryLiabilitySection editedFields={{ solidaryLiability: value }} onFieldChange={() => {}} />);
  expect(screen.getByRole('radio', { name: label })).toBeChecked();
});

it.each([['true', 'Солидарное'], ['false', 'Несолидарное']])('записывает явное значение %s', (value, label) => {
  const change = jest.fn();
  render(<SolidaryLiabilitySection editedFields={{}} onFieldChange={change} />);
  fireEvent.click(screen.getByRole('radio', { name: label }));
  expect(change).toHaveBeenCalledWith('solidaryLiability', value);
});
