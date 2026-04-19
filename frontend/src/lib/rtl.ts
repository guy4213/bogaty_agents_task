export function isHebrew(text: string): boolean {
  return /[\u0590-\u05FF]/.test(text);
}
