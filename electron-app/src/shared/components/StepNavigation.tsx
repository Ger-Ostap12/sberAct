import React from 'react';
import { Box, Button, Typography } from '@mui/material';
import BackIcon from '@mui/icons-material/ArrowBack';
import HomeIcon from '@mui/icons-material/Home';

interface Props {
  title: string;
  onBack: () => void;
  onMainMenu?: () => void;
}

const StepNavigation: React.FC<Props> = ({ title, onBack, onMainMenu }) => (
  <Box component="nav" aria-label="Навигация по шагам" sx={{
    position: 'sticky', top: 0, zIndex: theme => theme.zIndex.appBar,
    bgcolor: 'background.paper', borderBottom: 1, borderColor: 'divider',
    display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 2,
    mb: 3, py: 1.5, px: 1,
  }}>
    <Button variant="outlined" onClick={onBack} startIcon={<BackIcon />}>Назад</Button>
    <Typography variant="h4" component="h1" sx={{ flex: '1 1 240px' }}>{title}</Typography>
    {onMainMenu && (
      <Button variant="outlined" onClick={onMainMenu} startIcon={<HomeIcon />}>
        В главное меню
      </Button>
    )}
  </Box>
);

export default StepNavigation;
