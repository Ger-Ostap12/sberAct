import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import EditableCard from '../EditableCard';

describe('EditableCard', () => {
  it('показывает заголовок и содержимое', () => {
    render(
      <EditableCard title="Обязательство 1" onRemove={() => {}} removeLabel="Удалить">
        <div>поля карточки</div>
      </EditableCard>
    );
    expect(screen.getByText('Обязательство 1')).toBeInTheDocument();
    expect(screen.getByText('поля карточки')).toBeInTheDocument();
  });

  it('вызывает onRemove по клику на кнопку удаления', () => {
    const onRemove = jest.fn();
    render(
      <EditableCard
        title="Залог 2"
        onRemove={onRemove}
        removeLabel="Удалить залог"
      >
        <div />
      </EditableCard>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Удалить залог' }));
    expect(onRemove).toHaveBeenCalledTimes(1);
  });
});
