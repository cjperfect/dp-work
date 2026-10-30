export type InstalledSkill = {
  id: string;
  name: string;
  description: string;
  source: string;
  url: string;
};

export type CatalogSkill = InstalledSkill & { installs?: number };
