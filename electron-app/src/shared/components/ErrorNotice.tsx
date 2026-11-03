import React, { useEffect, useState } from 'react';
import { Button, Typography } from '@mui/material';
import { parseBackendError } from '../lib/convertErrors';
import { recordFailure } from '../lib/diagnostics';
import DiagnosticDialog from './DiagnosticDialog';

export default function ErrorNotice({ error }: { error: unknown }) {
  const [failure, setFailure] = useState(() => parseBackendError(error));
  useEffect(() => { setFailure(recordFailure(error)); }, [error]);
  const [open, setOpen] = useState(false);
  return <>
    <Typography component="div">{failure.message}</Typography>
    {failure.hint && <Typography variant="body2" sx={{ mt: 0.5 }}>{failure.hint}</Typography>}
    <Typography variant="caption" component="div" sx={{ mt: 0.5 }}>Номер сбоя: {failure.incidentId}</Typography>
    <Button size="small" onClick={() => setOpen(true)}>Подробности</Button>
    <DiagnosticDialog open={open} onClose={() => setOpen(false)} incidentId={failure.incidentId} />
  </>;
}
