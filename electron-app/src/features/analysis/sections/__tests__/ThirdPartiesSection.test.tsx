import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ThirdPartiesSection from '../ThirdPartiesSection';
import { ThirdParty } from '../../../../types';

const tp = (over: Partial<ThirdParty> = {}): ThirdParty => ({
  id: 'tp-1',
  name: '',
  birthDate: '',
  address: '',
  inn: '',
  snils: '',
  ...over,
});

describe('ThirdPartiesSection — ОГРН по режиму', () => {
  it('банкротство: поля ОГРН нет', () => {
    render(
      <ThirdPartiesSection thirdParties={[tp()]} onUpdate={() => {}} onAdd={() => {}} onRemove={() => {}} />,
    );
    expect(screen.getByText('ИНН:')).toBeInTheDocument();
    expect(screen.queryByText('ОГРН:')).not.toBeInTheDocument();
  });

  it('ипотека: поле ОГРН показано', () => {
    render(
      <ThirdPartiesSection
        thirdParties={[tp()]}
        onUpdate={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
        mode="mortgage"
      />,
    );
    expect(screen.getByText('ОГРН:')).toBeInTheDocument();
  });

  it('ипотека: правка ОГРН вызывает onUpdate', () => {
    const onUpdate = jest.fn();
    render(
      <ThirdPartiesSection
        thirdParties={[tp({ ogrn: '1027700132195' })]}
        onUpdate={onUpdate}
        onAdd={() => {}}
        onRemove={() => {}}
        mode="mortgage"
      />,
    );
    fireEvent.change(screen.getByDisplayValue('1027700132195'), { target: { value: '1234567890123' } });
    expect(onUpdate).toHaveBeenCalledWith(0, 'ogrn', '1234567890123');
  });
});
