
import React, { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import CourtSection from '../CourtSection';
import { buildSubmitData } from '../../lib/buildSubmitData';
import { judgeSubstitutionError, resetJudgeSubstitution } from '../../lib/judgeSubstitution';
import { ExtractedData } from '../../../../types';

const main = 'Панова Кристина Олеговна';
const replacement = 'Тютюник Павел Николаевич';

const Form = () => {
  const [fields, setFields] = useState<Record<string, string>>({ judge: main });
  return <CourtSection editedFields={fields} onFieldChange={(key, value) => setFields(prev => ({ ...prev, [key]: value }))} />;
};

it('показывает второе поле только после включения и сохраняет основного судью', () => {
  render(<Form />);
  const toggle = screen.getByRole('button', { name: 'Взаимозамена' });
  expect(toggle).toHaveAttribute('aria-pressed', 'false');
  expect(screen.queryByRole('combobox', { name: 'Судья по взаимозамене' })).not.toBeInTheDocument();
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('combobox', { name: 'Судья' })).toHaveTextContent('Панова К.О.');
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Судья по взаимозамене' }));
  fireEvent.click(screen.getByRole('option', { name: 'Тютюник П.Н.' }));
  expect(screen.getByRole('combobox', { name: 'Судья по взаимозамене' })).toHaveTextContent('Тютюник П.Н.');
  fireEvent.click(toggle);
  expect(screen.queryByRole('combobox', { name: 'Судья по взаимозамене' })).not.toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: 'Судья' })).toHaveTextContent('Панова К.О.');
  fireEvent.click(toggle);
  expect(screen.getByRole('combobox', { name: 'Судья по взаимозамене' })).toHaveTextContent('Тютюник П.Н.');
});

it('не показывает взаимозамену в ипотеке', () => {
  render(<CourtSection editedFields={{ judgeSubstitutionEnabled: 'true' }} onFieldChange={() => {}} mode="mortgage" />);
  expect(screen.queryByRole('button', { name: 'Взаимозамена' })).not.toBeInTheDocument();
  expect(screen.queryByText('Судья по взаимозамене:')).not.toBeInTheDocument();
});

it('проверяет оба обязательных ФИО только при включённом режиме', () => {
  expect(judgeSubstitutionError({})).toBe('');
  expect(judgeSubstitutionError({ judgeSubstitutionEnabled: 'true' })).toMatch(/основного/);
  expect(judgeSubstitutionError({ judgeSubstitutionEnabled: 'true', judge: main })).toMatch(/по взаимозамене/);
  expect(judgeSubstitutionError({ judgeSubstitutionEnabled: 'true', judge: main, substituteJudge: replacement })).toBe('');
});

it('сбрасывает режим для нового заявления, сохраняя другие поля', () => {
  const fields = { judge: main, judgeSubstitutionEnabled: 'true', substituteJudge: replacement, substituteJudgeFullName: replacement };
  expect(resetJudgeSubstitution(fields)).toEqual({ judge: main });
  expect(fields.substituteJudge).toBe(replacement);
});

const submit = (enabled: string, category: 'bankruptcy' | 'mortgage' = 'bankruptcy') => {
  const analysisResult: ExtractedData = { documentType: 'rtk_application', confidence: 1,
    fields: {}, obligations: [], collaterals: [], thirdParties: [], debtors: [], rawText: '',
    metadata: { pageCount: 1, wordCount: 1, language: 'ru' } };
  return buildSubmitData({ analysisResult,
    editedFields: { judge: main, judgeSubstitutionEnabled: enabled, substituteJudge: replacement },
    entityType: 'individual', collateralOption: 'no_collateral', debtorStatus: null,
    applicationKind: 'rtk', selectedActs: [], documentCategory: category });
};

it('передаёт полное ФИО и инициалы каждого судьи с сохранением ролей', () => {
  expect(submit('true').fields).toMatchObject({ judge: 'Панова К.О.', judgeFullName: main,
    substituteJudge: 'Тютюник П.Н.', substituteJudgeFullName: replacement, judgeSubstitutionEnabled: 'true' });
});

it.each([['false', 'bankruptcy'], ['true', 'mortgage']] as const)('исключает неактивную взаимозамену: %s/%s', (enabled, category) => {
  const fields = submit(enabled, category).fields;
  expect(fields.substituteJudge).toBeUndefined();
  expect(fields.substituteJudgeFullName).toBeUndefined();
  expect(fields.judgeSubstitutionEnabled).toBeUndefined();
  expect(fields.judge).toBe('Панова К.О.');
});


it('не восстанавливает взаимозамену из прежних данных анализа после сброса формы', () => {
  const stale = { judge: main, judgeSubstitutionEnabled: 'true', substituteJudge: replacement };
  const analysisResult: ExtractedData = { documentType: 'rtk_application', confidence: 1,
    fields: stale, obligations: [], collaterals: [], thirdParties: [], debtors: [], rawText: '',
    metadata: { pageCount: 1, wordCount: 1, language: 'ru' } };
  const result = buildSubmitData({ analysisResult, editedFields: resetJudgeSubstitution(stale),
    entityType: 'individual', collateralOption: 'no_collateral', debtorStatus: null,
    applicationKind: 'rtk', selectedActs: [], documentCategory: 'bankruptcy' });
  expect(result.fields.judgeSubstitutionEnabled).toBeUndefined();
  expect(result.fields.substituteJudge).toBeUndefined();
  expect(analysisResult.fields.substituteJudge).toBe(replacement);
});
