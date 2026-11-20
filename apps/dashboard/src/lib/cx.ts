/** Joins truthy class names. */
export function cx(...names: Array<string | false | null | undefined>): string {
  return names.filter((name): name is string => typeof name === 'string' && name.length > 0).join(' ');
}
