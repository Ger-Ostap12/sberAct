import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TextField } from '@mui/material';
import FieldQualityMark from '../FieldQualityMark';
import { FieldQuality } from '../../../types';

/**
 * Подсветка поля, к которому у разбора есть претензия. Ключевое требование —
 * НЕ шуметь: 'medium' — обычное состояние почти всех полей формы, если подсвечивать
 * и его, юрист перестанет замечать настоящие проблемы.
 */
describe('FieldQualityMark', () => {
  const low: FieldQuality = {
    level: 'low',
    reasons: ['значение принадлежит полю «courtName», а не этому'],
    cleared: true,
  };

  const child = <TextField value="" onChange={() => {}} />;

  it('не помечает поле без данных о качестве', () => {
    render(<FieldQualityMark>{child}</FieldQualityMark>);
    expect(screen.queryByTestId('field-quality-low')).not.toBeInTheDocument();
  });

  it('не помечает medium — это обычное состояние, подсветка была бы шумом', () => {
    render(<FieldQualityMark quality={{ level: 'medium', reasons: [] }}>{child}</FieldQualityMark>);
    expect(screen.queryByTestId('field-quality-low')).not.toBeInTheDocument();
  });

  it('не помечает high', () => {
    render(
      <FieldQualityMark quality={{ level: 'high', reasons: ['реквизит проходит контрольную сумму ФНС'] }}>
        {child}
      </FieldQualityMark>,
    );
    expect(screen.queryByTestId('field-quality-low')).not.toBeInTheDocument();
  });

  it('помечает low', () => {
    render(<FieldQualityMark quality={low}>{child}</FieldQualityMark>);
    expect(screen.getByTestId('field-quality-low')).toBeInTheDocument();
  });

  it('очищенное поле — тултип требует ввести значение', async () => {
    render(<FieldQualityMark quality={low}>{child}</FieldQualityMark>);
    await userEvent.hover(screen.getByTestId('field-quality-low'));
    expect(await screen.findByText(/Поле очищено.*Введите верное значение/s)).toBeInTheDocument();
  });

  it('помеченное, но не очищенное — тултип просит сверить с документом', async () => {
    render(
      <FieldQualityMark quality={{ level: 'low', reasons: ['INN не проходит контрольную сумму'], cleared: false }}>
        {child}
      </FieldQualityMark>,
    );
    await userEvent.hover(screen.getByTestId('field-quality-low'));
    expect(await screen.findByText(/Проверьте по документу.*контрольную сумму/s)).toBeInTheDocument();
  });
});
