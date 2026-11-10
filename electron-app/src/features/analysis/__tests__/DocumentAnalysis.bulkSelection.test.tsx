import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import DocumentAnalysis from '../DocumentAnalysis';
import { DocumentData, ExtractedData, EntityType } from '../../../types';

const documentData: DocumentData = {
  filePath: 'test.docx', fileName: 'test.docx', fileSize: 1, uploadDate: new Date('2024-01-01'),
};
const setup = (entityType: EntityType = 'individual', fns = false) => {
  const done = jest.fn();
  const back = jest.fn();
  const menu = jest.fn();
  const data: ExtractedData = {
    documentType: 'rtk_application', confidence: 1, entityType: entityType === 'legal' ? 'legal' : 'individual',
    fields: { creditorName: fns ? 'ФНС России' : 'ПАО Сбербанк', courtName: 'Арбитражный суд', caseNumber: 'A-1' },
    obligations: [], collaterals: [], thirdParties: [], debtors: [], rawText: '',
    metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
  };
  render(<DocumentAnalysis documentData={documentData} extractedData={data}
    onAnalysisComplete={done} onBack={back} onMainMenu={menu} />);
  const names = { individual: 'Физ.лицо', legal: 'Юр.лицо', ip: 'ИП', kfh: 'Глава КФХ' };
  fireEvent.click(screen.getByRole('radio', { name: names[entityType] }));
  return { done, back, menu };
};
const action = (label: string, button: string) => fireEvent.click(within(
  screen.getByRole('group', { name: `Выбор актов: ${label}` }),
).getByRole('button', { name: button }));
const checkbox = (name: string | RegExp) => screen.getByRole('checkbox', { name });

it('меняет только выбранную группу и не включает недоступный залоговый акт', () => {
  setup();
  action('Принятие', 'Снять все');
  expect(checkbox('Определение о принятии')).not.toBeChecked();
  expect(checkbox('Общее отложение')).toBeChecked();
  action('Принятие', 'Выбрать все');
  expect(checkbox('Определение о принятии')).toBeChecked();
  expect(checkbox('Определение Б/Д нет ГП залог')).not.toBeChecked();
  expect(checkbox('Определение Б/Д нет ГП залог')).toBeDisabled();
});

it('снимает и выбирает промежуточные акты вместе с обоими отложениями', () => {
  setup();
  action('Промежуточные', 'Снять все');
  for (const name of ['Отложение', 'Общее отложение', 'Отложение 3 лицо', 'Общий возврат']) {
    expect(checkbox(name)).not.toBeChecked();
  }
  expect(checkbox('Определение о принятии')).toBeChecked();
  action('Промежуточные', 'Выбрать все');
  for (const name of ['Отложение', 'Общее отложение', 'Отложение 3 лицо', 'Общий возврат']) {
    expect(checkbox(name)).toBeChecked();
  }
});

it.each([
  ['individual', 'Решение реализация', 'Определение реструктуризация', 'Решение конкурсное'],
  ['ip', 'Решение реализация', 'Определение реструктуризация', 'Решение конкурсное'],
  ['legal', 'Решение конкурсное', 'Определение Наблюдение', 'Решение реализация'],
  ['kfh', 'Решение конкурсное', 'Определение Наблюдение', 'Решение реализация'],
])('массовый выбор финальных актов учитывает лицо %s', (entity, first, second, forbidden) => {
  setup(entity as EntityType);
  action('Финальные СА', 'Снять все');
  action('Финальные СА', 'Выбрать все');
  expect(checkbox(first)).toBeChecked();
  expect(checkbox(second)).toBeChecked();
  expect(checkbox(forbidden)).not.toBeChecked();
  expect(screen.queryByRole('checkbox', { name: 'Резолютивная часть' })).not.toBeInTheDocument();
});

it('ФНС: массовый выбор принятия не включает акты об отсутствующей госпошлине', () => {
  setup('individual', true);
  action('Принятие', 'Снять все');
  action('Принятие', 'Выбрать все');
  expect(checkbox('Определение Б/Д нет ГП')).not.toBeChecked();
  expect(checkbox('Определение Б/Д нет ГП')).toBeDisabled();
  expect(checkbox('Определение о принятии')).toBeChecked();
});

it('РТК: сохраняет один выбранный вид, снимает финальный акт и резолютивку, передаёт выбор дальше', () => {
  const { done } = setup();
  fireEvent.click(screen.getByRole('radio', { name: 'Включение в РТК' }));
  fireEvent.click(checkbox(/РТК реструктуризация/));
  action('Финальные СА', 'Снять все');
  expect(checkbox(/РТК реструктуризация/)).not.toBeChecked();
  expect(checkbox('Резолютивная часть')).not.toBeChecked();
  action('Финальные СА', 'Выбрать все');
  expect(checkbox(/РТК реструктуризация/)).toBeChecked();
  expect(checkbox(/РТК реализация/)).not.toBeChecked();
  expect(checkbox(/За реестр/)).not.toBeChecked();
  expect(checkbox('Резолютивная часть')).toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
  expect(done).toHaveBeenCalledTimes(1);
  expect(done.mock.calls[0][0].fields.final_rtk_inclusion_variant).toBe('restructuring');
});

it('после снятия всех актов не позволяет продолжить с пустым выбором', () => {
  setup();
  for (const label of ['Принятие', 'Промежуточные', 'Финальные СА']) action(label, 'Снять все');
  expect(screen.getByRole('button', { name: 'Продолжить' })).toBeDisabled();
});

it('закреплённая навигация вызывает переход назад и в главное меню', () => {
  const { back, menu } = setup();
  const navigation = screen.getByRole('navigation', { name: 'Навигация по шагам' });
  expect(navigation).toHaveStyle({ position: 'sticky', top: '0px' });
  fireEvent.click(within(navigation).getByRole('button', { name: 'Назад' }));
  expect(back).toHaveBeenCalledTimes(1);
  expect(menu).not.toHaveBeenCalled();
  fireEvent.click(within(navigation).getByRole('button', { name: 'В главное меню' }));
  expect(menu).toHaveBeenCalledTimes(1);
});
