import React from 'react';
import { render } from '@testing-library/react';
import DocumentPreview from '../DocumentPreview';
import { ALL_TEMPLATES } from '../../../templates';
import { ExtractedData } from '../../../types';

// Базовый снапшот вывода предпросмотра по КАЖДОМУ шаблону. Фиксирует текущий
// (до config-изации getTemplatePreview) рендер, чтобы поймать любое расхождение
// после рефакторинга. Значения полей — детерминированные заглушки.
const sampleData = (): ExtractedData => ({
  documentType: 'rtk_application',
  confidence: 1,
  entityType: 'legal',
  fields: {
    applicantName: 'ООО «Ромашка»',
    applicantAddress: '344000, г. Ростов-на-Дону, ул. Ленина, д. 1',
    courtName: 'Арбитражный суд Ростовской области',
    caseNumber: 'А53-12345/2024',
    creditorName: 'ПАО Сбербанк',
    debtorName: 'Иванов Иван Иванович',
    principalDebt: '100000',
    loanDebt: '90000',
    interest: '5000',
    penalties: '1000',
    forfeit: '2000',
    totalDebt: '108000',
    principalDebt13: '100000',
    interest14: '5000',
    forfeit15: '2000',
    stateDuty16: '3240',
    creditAmount: '500000',
    inn: '6100000000',
    ogrn: '1026100000000',
    ogrnip: '304616900000000',
    bankCommission: '500',
    kfhHeadName: 'Петров Пётр Петрович',
    mortgageCollateralDescription1221: 'Квартира, 61:44:0010203:15',
    ipCollateralContractNumber: 'ДЗ-1',
    ipCollateralContractDate: '01.02.2024',
    ipCollateralClaimAmount: '108000',
    mortgageCreditAmount111: '500000',
    mortgageStartingPrice1225: '400000',
    mortgageCourtName002: 'Арбитражный суд Ростовской области',
    mortgageCourtAddress001: '344000, г. Ростов-на-Дону',
    mortgageRepresentative22: 'Сидоров С.С.',
    debtSnapshotDate88: '01.01.2024',
  },
  obligations: [],
  collaterals: [],
  rawText: '',
  metadata: { pageCount: 1, wordCount: 1, language: 'ru' },
});

describe('DocumentPreview — снапшот предпросмотра по шаблонам', () => {
  ALL_TEMPLATES.forEach((tpl) => {
    it(`шаблон ${tpl.id}`, () => {
      const { container } = render(
        <DocumentPreview
          extractedData={sampleData()}
          selectedTemplate={tpl}
          onDocumentGenerated={() => {}}
          onBack={() => {}}
          onNewDocument={() => {}}
        />
      );
      expect(container).toMatchSnapshot();
    });
  });
});
