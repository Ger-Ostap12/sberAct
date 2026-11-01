import React, { useState } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import RepresentativeSection from '../RepresentativeSection';
import { buildSubmitData } from '../../lib/buildSubmitData';
import { ExtractedData, MortgageKind, TemplateType } from '../../../../types';

import { useGenerateDocument } from '../../../preview/hooks/useGenerateDocument';
import { generateDocument } from '../../../../services/electronApi';

jest.mock('../../../../services/electronApi');
const send = generateDocument as jest.MockedFunction<typeof generateDocument>;
const template: TemplateType = {
  id: 'mortgage', name: 'Ипотека', category: 'Ипотека', description: '', fields: [],
};
beforeEach(() => send.mockResolvedValue({ success: true, document_id: 'test' }));
afterEach(() => jest.clearAllMocks());

const analysis = (): ExtractedData => ({
  documentType: 'mortgage_claim',
  confidence: 1,
  entityType: 'individual',
  fields: {
    representativeName: 'Орлов Олег Олегович',
    representativePoaFrom: '01.01.2020',
    representativePoaTo: '31.12.2020',
  },
  obligations: [],
  collaterals: [],
  thirdParties: [],
  debtors: [],
  rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

function Harness({ kind, onSubmit }: {
  kind: MortgageKind;
  onSubmit: (data: ExtractedData) => void;
}) {
  const source = analysis();
  const [fields, setFields] = useState<Record<string, string>>({
    representativeName: 'Орлов Олег Олегович',
    representativePoaFrom: '01.01.2020',
    representativePoaTo: '31.12.2020',
  });
  const data = buildSubmitData({
    analysisResult: source, editedFields: fields, entityType: null,
    collateralOption: null, debtorStatus: null, applicationKind: 'initiation',
    selectedActs: [], documentCategory: 'mortgage', mortgageKind: kind,
  });
  const generation = useGenerateDocument(data, template, () => {});
  return <>
    <RepresentativeSection editedFields={fields}
      onFieldChange={(key, value) => setFields((old) => ({ ...old, [key]: value }))} />
    <button onClick={() => { onSubmit(data); void generation.generate(); }}>
      Передать на генерацию
    </button>
  </>;
}

describe.each(['civil', 'ddu', 'military'] as const)('Доверенность: %s', (kind) => {
  it('обе даты, введённые вручную, передаются в формате ДД.ММ.ГГГГ', async () => {
    const submitted = jest.fn();
    const { container } = render(<Harness kind={kind} onSubmit={submitted} />);
    const dates = container.querySelectorAll('input[type="date"]');
    expect(dates).toHaveLength(2);
    fireEvent.change(dates[0], { target: { value: '2032-02-29' } });
    fireEvent.blur(dates[0]);
    fireEvent.change(dates[1], { target: { value: '2034-08-22' } });
    fireEvent.blur(dates[1]);
    await act(async () => { fireEvent.click(screen.getByText('Передать на генерацию')); });
    expect(send).toHaveBeenCalledTimes(1);
    expect(send.mock.calls[0][0].data).toMatchObject({
      representativePoaFrom: '29.02.2032', representativePoaTo: '22.08.2034',
    });
    expect(send.mock.calls[0][0].data.fields).toBeUndefined();
    expect(submitted).toHaveBeenCalledTimes(1);
    expect(submitted.mock.calls[0][0].fields).toMatchObject({
      representativeName: 'Орлов Олег Олегович',
      representativePoaFrom: '29.02.2032',
      representativePoaTo: '22.08.2034',
      selectedMortgageKind: kind,
    });
  });

  it.each([false, true])('очищенные даты не заменяются прежними: обе=%s', async (both) => {
    const submitted = jest.fn();
    const { container } = render(<Harness kind={kind} onSubmit={submitted} />);
    const dates = container.querySelectorAll('input[type="date"]');
    if (both) {
      fireEvent.change(dates[0], { target: { value: '' } });
      fireEvent.blur(dates[0]);
    }
    fireEvent.change(dates[1], { target: { value: '' } });
    fireEvent.blur(dates[1]);
    await act(async () => { fireEvent.click(screen.getByText('Передать на генерацию')); });
    expect(send.mock.calls[0][0].data.representativePoaTo).toBe('');
    expect(submitted.mock.calls[0][0].fields.representativePoaTo).toBe('');
    expect(submitted.mock.calls[0][0].fields.representativePoaFrom)
      .toBe(both ? '' : '01.01.2020');
  });
});
