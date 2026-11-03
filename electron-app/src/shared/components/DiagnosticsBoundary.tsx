import React from 'react';
import { Alert, Button } from '@mui/material';
import { appendEvent, recordFailure } from '../lib/diagnostics';
import type { BackendFailure } from '../lib/convertErrors';
import ErrorNotice from './ErrorNotice';

export default class DiagnosticsBoundary extends React.Component<React.PropsWithChildren,
  { error: unknown; failure: BackendFailure | null }> {
  state: { error: unknown; failure: BackendFailure | null } = { error: null, failure: null };
  static getDerivedStateFromError(error: unknown) { return { error }; }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    const failure = recordFailure(error, 'Не удалось отобразить экран.');
    if (info.componentStack) appendEvent({ time: new Date().toISOString(), component: 'interface',
      level: 'error', message: info.componentStack, incidentId: failure.incidentId, operation: 'Отображение экрана' });
    this.setState({ failure });
  }
  render() {
    if (this.state.error) return <Alert severity="error">
      {this.state.failure ? <ErrorNotice error={this.state.failure} /> : 'Не удалось отобразить экран.'}
      <Button onClick={() => window.location.reload()}>Перезагрузить приложение</Button>
    </Alert>;
    return this.props.children;
  }
}
