import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DeceasedSection from '../DeceasedSection';
import { Heir } from '../../../../types';

const heirs: Heir[] = [
  { id: 'heir-1', name: 'Ким Эмма Николаевна', address: '346744, Ростовская обл., с. Кулешовка' },
];

const noop = () => {};

const renderSection = (props: Partial<React.ComponentProps<typeof DeceasedSection>> = {}) =>
  render(
    <DeceasedSection
      editedFields={{}}
      onFieldChange={noop}
      heirs={[]}
      onHeirUpdate={noop}
      onHeirAdd={noop}
      onHeirRemove={noop}
      {...props}
    />,
  );

// Блок «Сведения о смерти»: дата смерти и наследники подтягиваются из заявления,
// нотариус и свидетельство вводятся вручную.
describe('DeceasedSection', () => {
  it('рендерит поля и заполняет из editedFields', () => {
    renderSection({
      editedFields: {
        notaryName: 'Петров Сергей Иванович',
        notaryAddress: '344002, г. Ростов-на-Дону, ул. Садовая, д. 5',
        deathDate: '24.02.2019',
        deathCertificate: 'II-МЮ № 123456',
      },
    });
    expect(screen.getByText('Сведения о смерти')).toBeInTheDocument();
    expect(screen.getByText('ФИО нотариуса:')).toBeInTheDocument();
    expect(screen.getByText('Адрес нотариуса:')).toBeInTheDocument();
    expect(screen.getByText('Дата смерти:')).toBeInTheDocument();
    expect(screen.getByText('Свидетельство о смерти:')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Петров Сергей Иванович')).toBeInTheDocument();
    expect(screen.getByDisplayValue('24.02.2019')).toBeInTheDocument();
    expect(screen.getByDisplayValue('II-МЮ № 123456')).toBeInTheDocument();
  });

  it('маскирует дату смерти в дд.мм.гггг', () => {
    const onFieldChange = jest.fn();
    renderSection({ onFieldChange });
    fireEvent.change(screen.getByPlaceholderText('дд.мм.гггг'), { target: { value: '24022019' } });
    expect(onFieldChange).toHaveBeenCalledWith('deathDate', '24.02.2019');
  });

  it('показывает ошибку на несуществующей дате смерти', () => {
    const { rerender } = renderSection({ editedFields: { deathDate: '31.02.2025' } });
    expect(screen.getByText('Введите существующую дату в формате дд.мм.гггг')).toBeInTheDocument();

    rerender(
      <DeceasedSection
        editedFields={{ deathDate: '28.02.2025' }}
        onFieldChange={noop}
        heirs={[]}
        onHeirUpdate={noop}
        onHeirAdd={noop}
        onHeirRemove={noop}
      />,
    );
    expect(screen.queryByText('Введите существующую дату в формате дд.мм.гггг')).not.toBeInTheDocument();
  });

  it('чистит недопустимые символы в свидетельстве', () => {
    const onFieldChange = jest.fn();
    renderSection({ onFieldChange });
    fireEvent.change(screen.getByPlaceholderText('II-МЮ № 123456'), { target: { value: 'ii-мю № 123456!' } });
    expect(onFieldChange).toHaveBeenCalledWith('deathCertificate', 'II-МЮ № 123456');
  });

  const CERT_ERROR = 'Формат: римская серия, две русские буквы и шесть цифр — II-МЮ № 123456';

  it('показывает ошибку на битом свидетельстве и молчит на корректном', () => {
    renderSection({ editedFields: { deathCertificate: 'II-МЮ № 12345' } });
    expect(screen.getByText(CERT_ERROR)).toBeInTheDocument();
  });

  it('корректное свидетельство ошибкой не считается', () => {
    renderSection({ editedFields: { deathCertificate: 'II-МЮ № 123456' } });
    expect(screen.queryByText(CERT_ERROR)).not.toBeInTheDocument();
  });

  it('незаполненные поля ошибкой не считаются', () => {
    renderSection();
    expect(screen.queryByText('Введите существующую дату в формате дд.мм.гггг')).not.toBeInTheDocument();
    expect(screen.queryByText(CERT_ERROR)).not.toBeInTheDocument();
  });

  it('рендерит карточку наследника из данных заявления', () => {
    renderSection({ heirs });
    expect(screen.getByText('Наследник 1')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Ким Эмма Николаевна')).toBeInTheDocument();
    expect(screen.getByDisplayValue('346744, Ростовская обл., с. Кулешовка')).toBeInTheDocument();
  });

  it('позволяет добавить и удалить наследника — их может быть несколько', () => {
    const onHeirAdd = jest.fn();
    const onHeirRemove = jest.fn();
    renderSection({ heirs, onHeirAdd, onHeirRemove });

    fireEvent.click(screen.getByRole('button', { name: 'Добавить наследника' }));
    expect(onHeirAdd).toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Удалить наследника' }));
    expect(onHeirRemove).toHaveBeenCalledWith(0);
  });

  it('правка наследника уходит с его индексом', () => {
    const onHeirUpdate = jest.fn();
    renderSection({ heirs, onHeirUpdate });
    fireEvent.change(screen.getByDisplayValue('Ким Эмма Николаевна'), { target: { value: 'Ким Э. Н.' } });
    expect(onHeirUpdate).toHaveBeenCalledWith(0, 'name', 'Ким Э. Н.');
  });

  it('без наследников показывает только кнопку добавления', () => {
    renderSection();
    expect(screen.queryByText('Наследник 1')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Добавить наследника' })).toBeInTheDocument();
  });
});
