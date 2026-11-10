import React from 'react';
import { Box, Grid, Typography } from '@mui/material';
import DateInput from '../components/DateInput';
import { LABEL_OVERLAP_BOX, LABEL_OVERLAP_SX, BLOCK_BOX_SX } from '../../../shared/styles/formStyles';

interface DatesSectionProps {
  editedFields: Record<string, string>;
  onFieldChange: (field: string, value: string) => void;
  mode?: 'bankruptcy' | 'mortgage';
}

const DatesSection: React.FC<DatesSectionProps> = ({ editedFields, onFieldChange, mode = 'bankruptcy' }) => {
  const mortgage = mode === 'mortgage';
  const fields: { field: string; label: string; allowText?: boolean; withTime?: boolean }[] = [
    { field: 'date', label: mortgage ? 'Дата принятия решения:' : 'Дата принятия определения:' },
    { field: 'courtSubmissionDate24', label: 'Дата направления в суд:' },
    ...(mortgage ? [{ field: 'noticeDate', label: 'Дата извещения:' }] : []),
    { field: 'applicationReceiptDate23', label: 'Дата поступления заявления в суд (согласно штампу):' },
    { field: 'objectionsDeadline18', label: 'Установка срока на предоставление возражений:', allowText: true },
    ...(!mortgage ? [
      { field: 'considerationDeadline19', label: 'На рассмотрение заявления в срок:', allowText: true },
      { field: 'withoutMovementDeadline20', label: 'Срок для оставления без движения:', allowText: true },
    ] : []),
    { field: 'courtHearingDateTime99', label: 'Дата и время судебного заседания:', withTime: true },
  ];
  return (
    <Box sx={{ ...BLOCK_BOX_SX, mb: 3 }}>
      <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>Даты и сроки</Typography>
      <Grid container spacing={2}>
        {fields.map(({ field, label, allowText, withTime }) => (
          <Grid item xs={12} sm={6} key={field}>
            <Box sx={LABEL_OVERLAP_BOX}>
              <Typography variant="body2" sx={LABEL_OVERLAP_SX}>{label}</Typography>
              <DateInput value={editedFields[field] || ''} onChange={value => onFieldChange(field, value)}
                label={label} allowText={allowText} withTime={withTime}
                calendarLabel={field === 'objectionsDeadline18' ? 'Выбрать дату в календаре' : undefined} />
            </Box>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
};

export default DatesSection;
