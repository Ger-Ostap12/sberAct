
import { isValidFio } from '../../../shared/lib/validators';

export const judgeSubstitutionError = (fields: Record<string, string>): string => {
  if (fields.judgeSubstitutionEnabled !== 'true') return '';
  if (!fields.judge?.trim()) return 'Для взаимозамены укажите основного судью';
  if (!fields.substituteJudge?.trim()) return 'Укажите судью по взаимозамене';
  if (!isValidFio(fields.judge) || !isValidFio(fields.substituteJudge)) {
    return 'ФИО судьи: Фамилия Имя Отчество или Фамилия И.О.';
  }
  return '';
};

export const resetJudgeSubstitution = (fields: Record<string, string>): Record<string, string> => {
  const result = { ...fields };
  delete result.judgeSubstitutionEnabled;
  delete result.substituteJudge;
  delete result.substituteJudgeFullName;
  return result;
};
