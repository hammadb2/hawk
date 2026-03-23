import { MetadataRoute } from 'next'

export default function sitemap(): MetadataRoute.Sitemap {
  const base = 'https://hawk.akbstudios.com'
  return [
    { url: base, lastModified: new Date(), changeFrequency: 'weekly', priority: 1 },
    { url: `${base}/features`, lastModified: new Date(), changeFrequency: 'monthly', priority: 0.9 },
    { url: `${base}/pricing`, lastModified: new Date(), changeFrequency: 'monthly', priority: 0.9 },
    { url: `${base}/features/breach-check`, lastModified: new Date(), changeFrequency: 'monthly', priority: 0.8 },
    { url: `${base}/features/domain-monitoring`, lastModified: new Date(), changeFrequency: 'monthly', priority: 0.8 },
    { url: `${base}/features/lookalike-domain`, lastModified: new Date(), changeFrequency: 'monthly', priority: 0.8 },
    { url: `${base}/blog`, lastModified: new Date(), changeFrequency: 'weekly', priority: 0.7 },
  ]
}
