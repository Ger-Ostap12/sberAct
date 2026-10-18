import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import CreditorSection from '../CreditorSection';

// Почтовый адрес кредитора: в заявлении не ищется, юрист вводит его сам.

const noop = () => {};

describe('CreditorSection — почтовый адрес', () => {
  it('поле есть в банкротстве', () => {
    render(
      <CreditorSection editedFields={{}} onFieldChange={noop} onCreditorChange={noop} banks={[]} />,
    );
    expect(screen.getByText('Почтовый адрес кредитора:')).toBeInTheDocument();
  });

  it('в ипотеке подпись про истца', () => {
    render(
      <CreditorSection editedFields={{}} onFieldChange={noop} onCreditorChange={noop} banks={[]} mode="mortgage" />,
    );
    expect(screen.getByText('Почтовый адрес истца:')).toBeInTheDocument();
  });

  it('показывает введённое значение', () => {
    render(
      <CreditorSection
        editedFields={{ creditorPostalAddress: '109052, г. Москва, ул. Смирновская, д. 10' }}
        onFieldChange={noop}
        onCreditorChange={noop}
        banks={[]}
      />,
    );
    expect(screen.getByDisplayValue('109052, г. Москва, ул. Смирновская, д. 10')).toBeInTheDocument();
  });

  it('правка уходит в поле creditorPostalAddress, а не в юридический адрес', () => {
    const изменения: Array<[string, string]> = [];
    render(
      <CreditorSection
        editedFields={{}}
        onFieldChange={(поле, значение) => изменения.push([поле, значение])}
        onCreditorChange={noop}
        banks={[]}
      />,
    );
    const поле = screen.getByPlaceholderText('109052, г. Москва, ул. Смирновская, д. 10, стр. 22');
    fireEvent.change(поле, { target: { value: '344002, г. Ростов-на-Дону' } });
    fireEvent.blur(поле);
    expect(изменения).toEqual([['creditorPostalAddress', '344002, г. Ростов-на-Дону']]);
  });

  it('юридический и почтовый адреса — разные поля', () => {
    render(
      <CreditorSection
        editedFields={{
          creditorAddress: '117312, г. Москва, ул. Вавилова, д. 19',
          creditorPostalAddress: '109052, г. Москва, ул. Смирновская, д. 10',
        }}
        onFieldChange={noop}
        onCreditorChange={noop}
        banks={[]}
      />,
    );
    expect(screen.getByDisplayValue('117312, г. Москва, ул. Вавилова, д. 19')).toBeInTheDocument();
    expect(screen.getByDisplayValue('109052, г. Москва, ул. Смирновская, д. 10')).toBeInTheDocument();
  });
});
