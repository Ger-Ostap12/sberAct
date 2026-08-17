import React from 'react';
import ReactDOM from 'react-dom/client';
// Шрифт темы MUI (см. App.tsx). Раньше тянулся с fonts.googleapis.com и на
// машине без интернета не грузился вовсе — здесь он попадает в бандл.
// Начертания те же, что запрашивала прежняя ссылка: 300/400/500/700.
import '@fontsource/roboto/300.css';
import '@fontsource/roboto/400.css';
import '@fontsource/roboto/500.css';
import '@fontsource/roboto/700.css';
import App from './App';

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
