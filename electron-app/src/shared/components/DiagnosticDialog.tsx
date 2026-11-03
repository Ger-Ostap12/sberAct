import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material';
import { collectReport, copyReport, diagnosticEntries, saveReport, subscribeDiagnostics, recordFailure } from '../lib/diagnostics';

export default function DiagnosticDialog({ open, onClose, incidentId }: {
  open: boolean; onClose: () => void; incidentId?: string;
}) {
  const [entries, setEntries] = useState(diagnosticEntries);
  const [report, setReport] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    let active = true;
    setNotice('');
    const stop = subscribeDiagnostics(() => setEntries(diagnosticEntries()));
    setEntries(diagnosticEntries());
    collectReport().then(value => { if (active) setReport(value); });
    return () => { active = false; stop(); };
  }, [open]);
  const action = async (save: boolean) => {
    setBusy(true);
    try {
      const latest = await collectReport();
      setReport(latest);
      if (save) setNotice(await saveReport(latest) ? 'Отчёт сохранён.' : 'Сохранение отменено.');
      else { await copyReport(latest); setNotice('Отчёт скопирован.'); }
    } catch (error) {
      const failure = recordFailure(error, 'Не удалось скопировать или сохранить отчёт.');
      setNotice(failure.message + ' Номер сбоя: ' + failure.incidentId);
    } finally { setBusy(false); }
  };
  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
    <DialogTitle>Диагностика приложения</DialogTitle>
    <DialogContent>
      {incidentId && <Typography sx={{ mb: 1 }}>Номер сбоя: {incidentId}</Typography>}
      <Typography variant="body2" sx={{ mb: 2 }}>
        Здесь собраны сообщения интерфейса и сервисов. Сохраните отчёт и передайте его разработчику.
      </Typography>
      {notice && <Alert severity="info" sx={{ mb: 1 }}>{notice}</Alert>}
      <Box component="pre" sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere',
        maxHeight: '50vh', overflow: 'auto', fontSize: 12, bgcolor: 'grey.100', p: 2 }}>
        {entries.length ? entries.map(entry => entry.time + ' [' + entry.component + '] ' + (entry.operation || '') + ' ' +
          (entry.incidentId || '') + '\n' + entry.message).join('\n\n') : report || 'Сообщений пока нет.'}
      </Box>
    </DialogContent>
    <DialogActions>
      <Button disabled={busy} onClick={() => void action(false)}>Копировать ошибку</Button>
      <Button disabled={busy} onClick={() => void action(true)}>Сохранить отчёт</Button>
      <Button onClick={onClose}>Закрыть</Button>
    </DialogActions>
  </Dialog>;
}
