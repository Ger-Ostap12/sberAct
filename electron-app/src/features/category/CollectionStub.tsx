import React from 'react';
import { Box, Typography, Button, Card, CardContent } from '@mui/material';
import BackIcon from '@mui/icons-material/ArrowBack';
import ConstructionIcon from '@mui/icons-material/Construction';

interface CollectionStubProps {
  onBack: () => void;
}

/** Заглушка режима «Взыскание» — раздел в разработке. */
const CollectionStub: React.FC<CollectionStubProps> = ({ onBack }) => (
  <Box sx={{ width: '100%', maxWidth: 800, mx: 'auto', px: 1 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
      <Button variant="outlined" onClick={onBack} startIcon={<BackIcon />} sx={{ mr: 2 }}>
        Назад
      </Button>
      <Typography variant="h4" component="h1">
        Взыскание
      </Typography>
    </Box>

    <Card>
      <CardContent sx={{ textAlign: 'center', py: 8 }}>
        <ConstructionIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
        <Typography variant="h6" gutterBottom>
          Раздел находится в разработке
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Обработка заявлений о взыскании появится в одной из следующих версий.
        </Typography>
      </CardContent>
    </Card>
  </Box>
);

export default CollectionStub;
