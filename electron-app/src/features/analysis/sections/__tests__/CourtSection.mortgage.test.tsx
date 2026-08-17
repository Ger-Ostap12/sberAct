import React from 'react';
import { render, screen } from '@testing-library/react';
import CourtSection from '../CourtSection';

describe('CourtSection — режим ипотеки', () => {
  it('банкротство: судья — выпадающий список, полей суда нет', () => {
    render(<CourtSection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.queryByText('Эл. почта суда:')).not.toBeInTheDocument();
    expect(screen.queryByText('Адрес сайта суда:')).not.toBeInTheDocument();
  });

  it('ипотека: добавлены адрес/почта/сайт суда и вышестоящая инстанция', () => {
    render(<CourtSection editedFields={{}} onFieldChange={() => {}} mode="mortgage" />);
    expect(screen.getByText('Адрес суда:')).toBeInTheDocument();
    expect(screen.getByText('Эл. почта суда:')).toBeInTheDocument();
    expect(screen.getByText('Адрес сайта суда:')).toBeInTheDocument();
    expect(screen.getByText('Вышестоящая инстанция:')).toBeInTheDocument();
  });

  it('ипотека: «Номер обособленного спора» скрыт (есть в банкротстве)', () => {
    const { rerender } = render(<CourtSection editedFields={{}} onFieldChange={() => {}} />);
    expect(screen.getByText('Номер обособленного спора:')).toBeInTheDocument();
    rerender(<CourtSection editedFields={{}} onFieldChange={() => {}} mode="mortgage" />);
    expect(screen.queryByText('Номер обособленного спора:')).not.toBeInTheDocument();
  });

  it('ипотека: невалидный email/URL подсвечиваются', () => {
    render(
      <CourtSection
        editedFields={{ courtEmail: 'нет-собаки', courtSite: 'без-схемы.ру' }}
        onFieldChange={() => {}}
        mode="mortgage"
      />,
    );
    expect(screen.getByText('Некорректный email')).toBeInTheDocument();
    expect(screen.getByText('Некорректный адрес (нужен http/https)')).toBeInTheDocument();
  });

  it('ипотека: валидные значения — без ошибок', () => {
    render(
      <CourtSection
        editedFields={{
          courtEmail: 'voroshilovsky.ros@sudrf.ru',
          courtSite: 'https://voroshilovsky--ros.sudrf.ru/',
        }}
        onFieldChange={() => {}}
        mode="mortgage"
      />,
    );
    expect(screen.queryByText('Некорректный email')).not.toBeInTheDocument();
    expect(screen.queryByText(/Некорректный адрес/)).not.toBeInTheDocument();
  });
});
