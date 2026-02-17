import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Grid,
  TextField,
  Chip,
  Alert,
  CircularProgress,
  Divider,
  Paper,
  Select,
  MenuItem,
  FormControl,
  InputLabel
} from '@mui/material';
import { ArrowBack as BackIcon, CheckCircle as CheckIcon } from '@mui/icons-material';
import { DocumentData, ExtractedData, Obligation } from '../types';

// Данные банков для автозаполнения
const BANK_DATA: Record<string, { address: string; ogrn: string; inn: string }> = {
  'ПАО ВТБ Банк': {
    address: '191144, г. Санкт-Петербург, пер. Дегтярный, д. 11 литер а',
    ogrn: '1027739609391',
    inn: '7702070139'
  },
  'Т-банк': {
    address: 'г. Москва, вн. тер. г. Муниципальный округ Савеловский, ул. Хуторская 2-Я, д. 38а, стр. 26',
    ogrn: '1027739642281',
    inn: '7710140679'
  },
  'Альфа банк': {
    address: '107078, г. Москва, ул. Каланчевская, д.27',
    ogrn: '1027700067328',
    inn: '7728168971'
  },
  'МТС банк': {
    address: '115432, г. Москва, пр-т Андропова, д. 18, корп. 1.',
    ogrn: '1027739053704',
    inn: '7702045051'
  },
  'банк Центр-инвест': {
    address: '344000, г. Ростов-на-Дону, пр. Соколова, д. 62.',
    ogrn: '1026100001949',
    inn: '6163011391'
  },
  'ПСБ банк': {
    address: '150003, Ярославская область, г. Ярославль, ул. Республиканская, д. 16',
    ogrn: '1027739019142',
    inn: '7744000912'
  },
  'Газпромбанк': {
    address: '117420, г. Москва, ул. Намёткина, д. 16, корп. 1.',
    ogrn: '1027700167110',
    inn: '7744001497'
  },
  'СберБанк': {
    address: 'г. Москва, вн. тер. г. муниципальный округ Академический, ул. Вавилова, д. 19',
    ogrn: '1027700132195',
    inn: '7707083893'
  }
};

const BANK_NAMES = Object.keys(BANK_DATA);

// Список судей
const JUDGES = [
  'Абдулина Светлана Витальевна',
  'Агальцова Ксения Владимировна',
  'Алмазова Зинаида Петровна',
  'Андрианова Юлия Юрьевна',
  'Апостолова Ольга Фёдоровна',
  'Бабаян Валентина Гарегиновна',
  'Батурина Екатерина Александровна',
  'Бондарева Зоя Ивановна',
  'Бондарчук Елена Владимировна',
  'Бруевич Валентина Сергеевна',
  'Бычкова Ольга Геннадиевна',
  'Власова Наталья Юрьевна',
  'Волуйских Илья Игоревич',
  'Ганюшкина Ольга Борисовна',
  'Гафиулина Анна Васильевна',
  'Демченко Ольга Александровна',
  'Ерёмин Филипп Фёдорович',
  'Жигало Наталья Александровна',
  'Захарова Виктория Михайловна',
  'Захарченко Ольга Петровна',
  'Золотарёва Ольга Валерьевна',
  'Исаченко Анна Николаевна',
  'Капелюха Ольга Ивановна',
  'Ковалёва Валентина Юрьевна',
  'Козин Денис Васильевич',
  'Колесник Ирина Валентиновна',
  'Комурджиева Ирина Петровна',
  'Комягин Виталий Михайлович',
  'Конева Марина Александровна',
  'Константинов Дмитрий Валентинович',
  'Королькова Нелли Николаевна',
  'Корх Сергей Эдуардович',
  'Косулина Екатерина Олеговна',
  'Кривоносова Ольга Валерьевна',
  'Кузина Наталия Владимировна',
  'Латышева Кристина Витальевна',
  'Лебедев Александр Михайлович',
  'Лебедева Юлия Валерьевна',
  'Лёвина Марьяна Алексеевна',
  'Ложечник Дмитрий Александрович',
  'Маковкина Ирина Владимировна',
  'Малыгина Марина Айдамировна',
  'Мариненко Екатерина Никитична',
  'Мацыпаева Елена Николаевна',
  'Меленчук Илья Сергеевич',
  'Мишаков Олег Григорьевич',
  'Новожилова Марина Александровна',
  'Овчаренко Наталия Николаевна',
  'Овчинникова Виктория Витальевна',
  'Палий Юлия Анатольевна',
  'Панова Кристина Олеговна',
  'Положий Кристина Владимировна',
  'Рябова Татьяна Павловна',
  'Сергеева Ксения Александровна',
  'Смородина Юлия Александровна',
  'Солуянова Татьяна Александровна',
  'Стрельникова Елена Сергеевна',
  'Танова Диана Григорьевна',
  'Тимина Екатерина Юрьевна',
  'Тютюник Павел Николаевич',
  'Фаргиева Ася Ибрагимовна',
  'Хатламаджиян Арташес Семенович',
  'Чумина Ксения Сергеевна',
  'Ширинская Ирина Борисовна',
  'Штрауб Валентина Леонидовна'
];

interface DocumentAnalysisProps {
  documentData: DocumentData;
  extractedData?: ExtractedData;
  onAnalysisComplete: (data: ExtractedData) => void;
  onBack: () => void;
}

const DocumentAnalysis: React.FC<DocumentAnalysisProps> = ({
  documentData,
  extractedData: propExtractedData,
  onAnalysisComplete,
  onBack
}) => {
  const [isAnalyzing, setIsAnalyzing] = useState(true);
  const [analysisResult, setAnalysisResult] = useState<ExtractedData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editedFields, setEditedFields] = useState<Record<string, string>>({});

  // Таймаут для предотвращения бесконечной загрузки
  useEffect(() => {
    const timeout = setTimeout(() => {
      if (isAnalyzing) {
        console.log('DocumentAnalysis: timeout reached, stopping analysis');
        setIsAnalyzing(false);
        setError('Превышено время ожидания анализа документа');
      }
    }, 25000); // 25 секунд

    return () => clearTimeout(timeout);
  }, [isAnalyzing]);

  useEffect(() => {
    // Анализ уже выполнен в DocumentUpload, данные переданы через props
    if (documentData) {
      console.log('DocumentAnalysis: documentData received:', documentData);

      if (propExtractedData) {
        // Используем данные, переданные через props
        console.log('DocumentAnalysis: received extractedData:', propExtractedData);
        console.log('DocumentAnalysis: obligations from extractedData:', propExtractedData.obligations);

        // Устанавливаем полный analysisResult с obligations
        const fullAnalysisResult = {
          ...propExtractedData,
          obligations: propExtractedData.obligations || []
        };
        console.log('DocumentAnalysis: setting full analysisResult:', fullAnalysisResult);
        console.log('DocumentAnalysis: obligations in fullAnalysisResult:', fullAnalysisResult.obligations);
        setAnalysisResult(fullAnalysisResult);

        const fields = propExtractedData.fields || {};
        console.log('DocumentAnalysis: fields from extractedData:', fields);

        // Устанавливаем статичные значения и фильтруем undefined
        const cleanFields: Record<string, string> = {};
        Object.keys(fields).forEach(key => {
          if (fields[key] !== undefined && fields[key] !== null) {
            cleanFields[key] = String(fields[key]);
            console.log(`DocumentAnalysis: setting field ${key} = ${cleanFields[key]}`);
          }
        });
        // Устанавливаем значения по умолчанию, если их нет
        if (!cleanFields.courtName) {
          cleanFields.courtName = "Арбитражный суд Ростовской области";
        }
        if (!cleanFields.creditorName) {
          cleanFields.creditorName = "ПАО Сбербанк";
        }
        // Синхронизируем связанные поля
        if (cleanFields.debtorName && !cleanFields.applicantName) {
          cleanFields.applicantName = cleanFields.debtorName;
        }
        if (cleanFields.applicantName && !cleanFields.debtorName) {
          cleanFields.debtorName = cleanFields.applicantName;
        }
        if (cleanFields.inn && !cleanFields.companyInn) {
          cleanFields.companyInn = cleanFields.inn;
        }
        if (cleanFields.companyInn && !cleanFields.inn) {
          cleanFields.inn = cleanFields.companyInn;
        }
        if (cleanFields.ogrnip && !cleanFields.ogrn) {
          cleanFields.ogrn = cleanFields.ogrnip;
        }
        // Синхронизируем loanDebt и principalDebt
        if (cleanFields.principalDebt && !cleanFields.loanDebt) {
          cleanFields.loanDebt = cleanFields.principalDebt;
        }
        if (cleanFields.loanDebt && !cleanFields.principalDebt) {
          cleanFields.principalDebt = cleanFields.loanDebt;
        }
        console.log('DocumentAnalysis: cleanFields after processing:', cleanFields);
        setEditedFields(cleanFields);
        setIsAnalyzing(false);
      } else {
        // Fallback: получаем данные из electronAPI
        console.log('DocumentAnalysis: no propExtractedData, trying electronAPI');
        const extractedData = (window as any).electronAPI?.getExtractedData();
        if (extractedData) {
          console.log('DocumentAnalysis: got data from electronAPI:', extractedData);
          setAnalysisResult(extractedData);
          const fields = extractedData.fields || {};
          const cleanFields: Record<string, string> = {};
          Object.keys(fields).forEach(key => {
            if (fields[key] !== undefined && fields[key] !== null) {
              cleanFields[key] = String(fields[key]);
            }
          });
          cleanFields.courtName = "Арбитражный суд Ростовской области";
          // creditorName берется из извлеченных данных (маркер [987])
          setEditedFields(cleanFields);
        } else {
          console.log('DocumentAnalysis: no data from electronAPI either');
        }
        setIsAnalyzing(false);
      }
    } else {
      console.log('DocumentAnalysis: no documentData');
      setIsAnalyzing(false);
    }
  }, [documentData, propExtractedData]);

  // Функция для форматирования сумм
  const formatAmount = (amount: string | number | undefined): string => {
    if (!amount) return '';
    const num = typeof amount === 'string' ? parseFloat(amount.replace(/[^\d.,]/g, '').replace(',', '.')) : amount;
    if (isNaN(num)) return String(amount);
    // Форматируем с пробелами для тысяч, но без символа валюты
    return new Intl.NumberFormat('ru-RU', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
      useGrouping: true
    }).format(num).replace(/\s/g, ' ');
  };

  // Функция для парсинга суммы из форматированной строки
  const parseAmount = (formattedAmount: string): string => {
    // Убираем все кроме цифр, точки и запятой
    return formattedAmount.replace(/[^\d.,]/g, '').replace(',', '.');
  };

  // Функция для обработки изменения суммы с форматированием при потере фокуса
  const handleAmountChange = (fieldName: string, value: string) => {
    // Сохраняем сырое значение (только цифры, точка или запятая)
    const rawValue = value.replace(/[^\d.,]/g, '').replace(',', '.');
    handleFieldChange(fieldName, rawValue);
  };

  // Функция для форматирования при потере фокуса
  const handleAmountBlur = (fieldName: string, value: string) => {
    const rawValue = value.replace(/[^\d.,]/g, '').replace(',', '.');
    if (rawValue && !isNaN(parseFloat(rawValue))) {
      const formatted = formatAmount(rawValue);
      handleFieldChange(fieldName, rawValue); // Сохраняем сырое значение для дальнейшей обработки
    }
  };

  const handleFieldChange = (fieldName: string, value: string) => {
    setEditedFields(prev => ({
      ...prev,
      [fieldName]: value
    }));
  };

  const handleCreditorChange = (value: string) => {
    if (value === 'OTHER') {
      // Если выбран "Другой банк", очищаем автозаполненные данные, но оставляем creditorName пустым для ручного ввода
      setEditedFields(prev => ({
        ...prev,
        creditorName: '',
        creditorAddress: '',
        creditorOgrn: '',
        creditorInn: ''
      }));
    } else if (value && BANK_DATA[value]) {
      // Если выбран банк из списка, автозаполняем данные
      const bankData = BANK_DATA[value];
      setEditedFields(prev => ({
        ...prev,
        creditorName: value,
        creditorAddress: bankData.address,
        creditorOgrn: bankData.ogrn,
        creditorInn: bankData.inn
      }));
    } else {
      // Если выбрано пустое значение, очищаем все поля кредитора
      setEditedFields(prev => ({
        ...prev,
        creditorName: '',
        creditorAddress: '',
        creditorOgrn: '',
        creditorInn: ''
      }));
    }
  };

  const handleContinue = () => {
    if (analysisResult) {
      // Объединяем извлеченные данные с отредактированными полями
      // Приоритет у отредактированных полей
      const updatedData: ExtractedData = {
        ...analysisResult,
        fields: {
          ...analysisResult.fields,
          ...editedFields
        }
      };

      // Убеждаемся, что все суммы передаются корректно
      // Синхронизируем loanDebt и principalDebt перед отправкой
      if (updatedData.fields) {
        if (updatedData.fields.loanDebt && !updatedData.fields.principalDebt) {
          updatedData.fields.principalDebt = updatedData.fields.loanDebt;
          updatedData.fields.principalDebt13 = updatedData.fields.loanDebt;
        } else if (updatedData.fields.principalDebt && !updatedData.fields.loanDebt) {
          updatedData.fields.loanDebt = updatedData.fields.principalDebt;
        }

        // Синхронизируем другие поля сумм
        if (updatedData.fields.interest && !updatedData.fields.interest14) {
          updatedData.fields.interest14 = updatedData.fields.interest;
        }
        if (updatedData.fields.interest14 && !updatedData.fields.interest) {
          updatedData.fields.interest = updatedData.fields.interest14;
        }

        if (updatedData.fields.forfeit && !updatedData.fields.forfeit15) {
          updatedData.fields.forfeit15 = updatedData.fields.forfeit;
        }
        if (updatedData.fields.forfeit15 && !updatedData.fields.forfeit) {
          updatedData.fields.forfeit = updatedData.fields.forfeit15;
        }

        if (updatedData.fields.penalties && !updatedData.fields.forfeit15) {
          updatedData.fields.forfeit15 = updatedData.fields.penalties;
          updatedData.fields.forfeit = updatedData.fields.penalties;
        }

        if (updatedData.fields.stateDuty && !updatedData.fields.stateDuty16) {
          updatedData.fields.stateDuty16 = updatedData.fields.stateDuty;
        }
        if (updatedData.fields.stateDuty16 && !updatedData.fields.stateDuty) {
          updatedData.fields.stateDuty = updatedData.fields.stateDuty16;
        }
      }

      console.log('DocumentAnalysis: sending updated data:', updatedData);
      console.log('DocumentAnalysis: editedFields:', editedFields);
      console.log('DocumentAnalysis: updatedData.fields:', updatedData.fields);
      console.log('DocumentAnalysis: creditorName in updatedData.fields:', updatedData.fields?.creditorName);
      console.log('DocumentAnalysis: inn in updatedData.fields:', updatedData.fields?.inn);
      console.log('DocumentAnalysis: loanDebt in updatedData.fields:', updatedData.fields?.loanDebt);
      console.log('DocumentAnalysis: principalDebt in updatedData.fields:', updatedData.fields?.principalDebt);
      console.log('DocumentAnalysis: stateDuty in updatedData.fields:', updatedData.fields?.stateDuty);
      console.log('DocumentAnalysis: judge in updatedData.fields:', updatedData.fields?.judge);
      console.log('DocumentAnalysis: date in updatedData.fields:', updatedData.fields?.date);
      onAnalysisComplete(updatedData);
    }
  };


  if (isAnalyzing) {
    return (
      <Box sx={{ textAlign: 'center', py: 8 }}>
        <CircularProgress size={64} sx={{ mb: 3 }} />
        <Typography variant="h5" gutterBottom>
          Анализируем документ...
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Извлекаем данные из заявления
        </Typography>
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ maxWidth: 600, mx: 'auto', textAlign: 'center' }}>
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
        <Button variant="outlined" onClick={onBack} startIcon={<BackIcon />}>
          Вернуться к загрузке
        </Button>
      </Box>
    );
  }

  if (!analysisResult) {
    return null;
  }

  const detectedEntityType =
    analysisResult.entityType ||
    (analysisResult.fields && (analysisResult.fields as any).entityType) ||
    'individual';

  const renderEntityIndicator = (label: string, active: boolean) => (
    <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
      <Box
        sx={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          bgcolor: active ? 'success.main' : 'grey.400',
          mr: 1
        }}
      />
      <Typography variant="body2" color={active ? 'text.primary' : 'text.secondary'}>
        {label}
      </Typography>
    </Box>
  );

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <Button
          variant="outlined"
          onClick={onBack}
          startIcon={<BackIcon />}
          sx={{ mr: 2 }}
        >
          Назад
        </Button>
        <Typography variant="h4" component="h1">
          Анализ документа
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {/* Информация о документе */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Информация о документе
              </Typography>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Файл: {documentData.fileName}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Размер: {(documentData.fileSize / 1024 / 1024).toFixed(2)} MB
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Дата загрузки: {documentData.uploadDate.toLocaleDateString('ru-RU')}
                </Typography>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Тип документа:
                </Typography>
                <Chip
                  label="Заявление о включении в РТК"
                  color="primary"
                  size="small"
                />
              </Box>

              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Тип должника:
                </Typography>
                {renderEntityIndicator('Физ лицо', detectedEntityType !== 'legal')}
                {renderEntityIndicator('Юр лицо', detectedEntityType === 'legal')}
              </Box>

            </CardContent>
          </Card>
        </Grid>

        {/* Извлеченные данные */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Извлеченные данные
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Проверьте и при необходимости отредактируйте извлеченные данные
              </Typography>

              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="ФИО/название должника"
                    value={editedFields.debtorName || editedFields.applicantName || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      handleFieldChange('debtorName', value);
                      handleFieldChange('applicantName', value);
                    }}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Адрес должника"
                    value={editedFields.applicantAddress || ''}
                    onChange={(e) => handleFieldChange('applicantAddress', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="ИНН"
                    value={editedFields.inn || editedFields.companyInn || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      handleFieldChange('inn', value);
                      handleFieldChange('companyInn', value);
                    }}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="ОГРНИП"
                    value={editedFields.ogrnip || editedFields.ogrn || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      handleFieldChange('ogrnip', value);
                      if (!editedFields.ogrn) {
                        handleFieldChange('ogrn', value);
                      }
                    }}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Название суда"
                    value={editedFields.courtName || ''}
                    onChange={(e) => handleFieldChange('courtName', e.target.value)}
                    size="small"
                    margin="dense"
                    placeholder="Арбитражный суд Ростовской области"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Номер дела"
                    value={editedFields.caseNumber || ''}
                    onChange={(e) => handleFieldChange('caseNumber', e.target.value)}
                    size="small"
                    margin="dense"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth size="small" margin="dense">
                    <Select
                      value={editedFields.judge || ''}
                      onChange={(e) => handleFieldChange('judge', e.target.value)}
                      displayEmpty
                      renderValue={(selected) => {
                        if (!selected) {
                          return <em>Выберите судью</em>;
                        }
                        return selected;
                      }}
                    >
                      <MenuItem value="">
                        <em>Выберите судью</em>
                      </MenuItem>
                      {JUDGES.map((judge) => (
                        <MenuItem key={judge} value={judge}>
                          {judge}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Дата"
                    type="date"
                    value={editedFields.date || ''}
                    onChange={(e) => handleFieldChange('date', e.target.value)}
                    size="small"
                    margin="dense"
                    InputLabelProps={{
                      shrink: true,
                    }}
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Комиссия Банка"
                    value={editedFields.bankCommission || ''}
                    onChange={(e) => {
                      const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                      handleFieldChange('bankCommission', value);
                    }}
                    size="small"
                    margin="dense"
                    placeholder="0.00"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth size="small" margin="dense">
                    <InputLabel shrink>Кредитор</InputLabel>
                    <Select
                      value={editedFields.creditorName && BANK_DATA[editedFields.creditorName] ? editedFields.creditorName : (editedFields.creditorName && !BANK_DATA[editedFields.creditorName] ? 'OTHER' : '')}
                      onChange={(e) => handleCreditorChange(e.target.value)}
                      label="Кредитор"
                      displayEmpty
                      notched
                    >
                      <MenuItem value="">
                        <em>Выберите банк</em>
                      </MenuItem>
                      {BANK_NAMES.map((bankName) => (
                        <MenuItem key={bankName} value={bankName}>
                          {bankName}
                        </MenuItem>
                      ))}
                      <MenuItem value="OTHER">
                        <em>Другой банк (ввести вручную)</em>
                      </MenuItem>
                    </Select>
                  </FormControl>
                  {(!editedFields.creditorName || (editedFields.creditorName && !BANK_DATA[editedFields.creditorName])) ? (
                    <TextField
                      fullWidth
                      label="Название кредитора"
                      value={editedFields.creditorName || ''}
                      onChange={(e) => handleFieldChange('creditorName', e.target.value)}
                      size="small"
                      margin="dense"
                      placeholder="Введите название банка вручную"
                      sx={{ mt: 1 }}
                    />
                  ) : null}
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Юридический адрес кредитора"
                    value={editedFields.creditorAddress || ''}
                    onChange={(e) => handleFieldChange('creditorAddress', e.target.value)}
                    size="small"
                    margin="dense"
                    placeholder="117312, г. Москва, ул. Вавилова, д. 19"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="ОГРН кредитора"
                    value={editedFields.creditorOgrn || ''}
                    onChange={(e) => handleFieldChange('creditorOgrn', e.target.value)}
                    size="small"
                    margin="dense"
                    placeholder="1027700132195"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="ИНН кредитора"
                    value={editedFields.creditorInn || ''}
                    onChange={(e) => handleFieldChange('creditorInn', e.target.value)}
                    size="small"
                    margin="dense"
                    placeholder="7707083893"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Ссудная задолженность"
                    value={editedFields.loanDebt || editedFields.principalDebt || ''}
                    onChange={(e) => {
                      const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                      handleFieldChange('loanDebt', value);
                      handleFieldChange('principalDebt', value);
                    }}
                    onBlur={(e) => {
                      const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                      if (value && !isNaN(parseFloat(value))) {
                        const formatted = formatAmount(value);
                        // Не форматируем в поле, оставляем сырое значение для удобства редактирования
                      }
                    }}
                    size="small"
                    margin="dense"
                    placeholder="0.00"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Гос пошлина"
                    value={editedFields.stateDuty || ''}
                    onChange={(e) => {
                      const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                      handleFieldChange('stateDuty', value);
                    }}
                    size="small"
                    margin="dense"
                    placeholder="0.00"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Проценты"
                    value={editedFields.interest || ''}
                    onChange={(e) => {
                      const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                      handleFieldChange('interest', value);
                    }}
                    size="small"
                    margin="dense"
                    placeholder="0.00"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Штрафные санкции"
                    value={editedFields.penalties || ''}
                    onChange={(e) => {
                      const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                      handleFieldChange('penalties', value);
                    }}
                    size="small"
                    margin="dense"
                    placeholder="0.00"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Неустойка"
                    value={editedFields.forfeit || ''}
                    onChange={(e) => {
                      const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                      handleFieldChange('forfeit', value);
                    }}
                    size="small"
                    margin="dense"
                    placeholder="0.00"
                  />
                </Grid>

                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Общая сумма долга"
                    value={editedFields.totalDebt || ''}
                    onChange={(e) => {
                      const value = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                      handleFieldChange('totalDebt', value);
                    }}
                    size="small"
                    margin="dense"
                    placeholder="0.00"
                  />
                </Grid>
              </Grid>

              {/* Финансовый управляющий */}
              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Финансовый управляющий
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="ФИО финансового управляющего"
                      value={editedFields.managerName || ''}
                      onChange={(e) => handleFieldChange('managerName', e.target.value)}
                      size="small"
                      margin="dense"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="Адрес проживания"
                      value={editedFields.managerAddress || ''}
                      onChange={(e) => handleFieldChange('managerAddress', e.target.value)}
                      size="small"
                      margin="dense"
                    />
                  </Grid>
                </Grid>
              </Box>

              {/* Третьи лица */}
              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2, color: 'primary.main' }}>
                  Третьи лица
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="ФИО третьего лица"
                      value={editedFields.thirdPartyName || ''}
                      onChange={(e) => handleFieldChange('thirdPartyName', e.target.value)}
                      size="small"
                      margin="dense"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="Адрес проживания"
                      value={editedFields.thirdPartyAddress || ''}
                      onChange={(e) => handleFieldChange('thirdPartyAddress', e.target.value)}
                      size="small"
                      margin="dense"
                    />
                  </Grid>
                </Grid>
              </Box>

              {/* Блок обязательств */}
              {(() => {
                console.log('DocumentAnalysis: rendering obligations:', analysisResult?.obligations);
                console.log('DocumentAnalysis: obligations length:', analysisResult?.obligations?.length);
                return null;
              })()}
              {analysisResult?.obligations && analysisResult.obligations.length > 0 && (
                <Box sx={{ mt: 3 }}>
                  <Typography variant="h6" gutterBottom sx={{ mb: 2 }}>
                    Обязательства
                  </Typography>
                  {analysisResult.obligations.map((obligation: Obligation, index: number) => (
                    <Card key={obligation.id} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0' }}>
                      <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                        Обязательство {index + 1}
                      </Typography>
                      <Grid container spacing={2}>
                        <Grid item xs={12} sm={4}>
                          <TextField
                            fullWidth
                            label="Номер договора"
                            value={obligation.contractNumber || ''}
                            onChange={(e) => {
                              const updatedObligations = [...(analysisResult.obligations || [])];
                              updatedObligations[index] = { ...obligation, contractNumber: e.target.value };
                              setAnalysisResult({ ...analysisResult, obligations: updatedObligations });
                            }}
                            size="small"
                            margin="dense"
                          />
                        </Grid>
                        <Grid item xs={12} sm={4}>
                          <TextField
                            fullWidth
                            label="Дата договора"
                            value={obligation.contractDate || ''}
                            onChange={(e) => {
                              const updatedObligations = [...(analysisResult.obligations || [])];
                              updatedObligations[index] = { ...obligation, contractDate: e.target.value };
                              setAnalysisResult({ ...analysisResult, obligations: updatedObligations });
                            }}
                            size="small"
                            margin="dense"
                          />
                        </Grid>
                        <Grid item xs={12} sm={4}>
                          <TextField
                            fullWidth
                            label="Тип обязательства"
                            value={obligation.obligationType || ''}
                            onChange={(e) => {
                              const updatedObligations = [...(analysisResult.obligations || [])];
                              updatedObligations[index] = { ...obligation, obligationType: e.target.value };
                              setAnalysisResult({ ...analysisResult, obligations: updatedObligations });
                            }}
                            size="small"
                            margin="dense"
                          />
                        </Grid>
                      </Grid>
                    </Card>
                  ))}
                </Box>
              )}

              <Grid container spacing={2} sx={{ mt: 1 }}>

                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="Дополнительная информация"
                    value={editedFields.additionalInfo || ''}
                    onChange={(e) => handleFieldChange('additionalInfo', e.target.value)}
                    size="small"
                    margin="dense"
                    multiline
                    rows={3}
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Box sx={{ textAlign: 'center', mt: 4 }}>
        <Button
          variant="contained"
          size="large"
          onClick={handleContinue}
          startIcon={<CheckIcon />}
          sx={{ px: 4 }}
        >
          Продолжить
        </Button>
      </Box>
    </Box>
  );
};

export default DocumentAnalysis;
