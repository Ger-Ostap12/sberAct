import React from 'react';
import { Box, Typography, Card, CardActionArea, CardContent, Button, Chip, Grid } from '@mui/material';
import {
  Gavel as BankruptcyIcon,
  AccountBalance as CollectionIcon,
  Home as MortgageIcon,
  ArrowBack as BackIcon,
} from '@mui/icons-material';
import { DocumentCategory, ExtractedData } from '../../types';
import { deriveCategory } from './lib/deriveCategory';

interface CategorySelectionProps {
  extractedData?: ExtractedData;
  onSelect: (category: DocumentCategory) => void;
  onBack: () => void;
}

interface CategoryOption {
  key: DocumentCategory;
  title: string;
  description: string;
  icon: React.ReactNode;
}

const OPTIONS: CategoryOption[] = [
  {
    key: 'bankruptcy',
    title: 'Банкротство',
    description: 'Полный анализ заявления о банкротстве и генерация судебных актов.',
    icon: <BankruptcyIcon sx={{ fontSize: 48 }} />,
  },
  {
    key: 'collection',
    title: 'Взыскание',
    description: 'Раздел находится в разработке.',
    icon: <CollectionIcon sx={{ fontSize: 48 }} />,
  },
  {
    key: 'mortgage',
    title: 'Ипотека',
    description: 'Заявление об обращении взыскания на заложенную недвижимость.',
    icon: <MortgageIcon sx={{ fontSize: 48 }} />,
  },
];

/** Меню выбора категории дела. Показывается после анализа, до формы полей.
 *  Рекомендованную категорию (по documentType) подсвечивает бейджем. */
const CategorySelection: React.FC<CategorySelectionProps> = ({
  extractedData,
  onSelect,
  onBack,
}) => {
  const recommended = deriveCategory(extractedData?.documentType);

  return (
    <Box sx={{ width: '100%', maxWidth: 1000, mx: 'auto', px: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <Button variant="outlined" onClick={onBack} startIcon={<BackIcon />} sx={{ mr: 2 }}>
          Назад
        </Button>
        <Typography variant="h4" component="h1">
          Выберите тип дела
        </Typography>
      </Box>

      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Рекомендованный тип подсвечен на основе анализа документа. При необходимости
        выберите другой.
      </Typography>

      <Grid container spacing={3}>
        {OPTIONS.map((opt) => {
          const isRecommended = opt.key === recommended;
          return (
            <Grid item xs={12} md={4} key={opt.key}>
              <Card
                sx={{
                  height: '100%',
                  border: isRecommended ? '2px solid' : '1px solid',
                  borderColor: isRecommended ? 'primary.main' : '#e0e0e0',
                  position: 'relative',
                }}
              >
                {isRecommended && (
                  <Chip
                    label="Рекомендуется"
                    color="primary"
                    size="small"
                    sx={{ position: 'absolute', top: 8, right: 8, zIndex: 1 }}
                  />
                )}
                <CardActionArea
                  onClick={() => onSelect(opt.key)}
                  sx={{ height: '100%' }}
                  aria-label={`Выбрать: ${opt.title}`}
                >
                  <CardContent sx={{ textAlign: 'center', py: 4 }}>
                    <Box sx={{ color: isRecommended ? 'primary.main' : 'text.secondary', mb: 2 }}>
                      {opt.icon}
                    </Box>
                    <Typography variant="h6" gutterBottom>
                      {opt.title}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {opt.description}
                    </Typography>
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grid>
          );
        })}
      </Grid>
    </Box>
  );
};

export default CategorySelection;
