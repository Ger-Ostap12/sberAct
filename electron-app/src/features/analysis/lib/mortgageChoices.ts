export const mortgageChoicesError = (fields: Record<string, string | undefined>): string | null => {
  if (fields.solidaryLiability !== 'true' && fields.solidaryLiability !== 'false') {
    return 'Выберите солидарное или несолидарное взыскание';
  }
  if (!['full', 'partial', 'deny'].includes(fields.claimResolution || '')) {
    return 'Выберите исход удовлетворения иска';
  }
  return null;
};

export const resetMortgageChoices = (fields: Record<string, string>): Record<string, string> => {
  const result = { ...fields };
  delete result.solidaryLiability;
  delete result.claimResolution;
  return result;
};
