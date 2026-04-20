---
version: 1
last_updated: 2026-04-18
experiment_id: exp-2026-04-18
---

# Baseline Configuration

Ecris TOUJOURS les emails en français.
Leads viennent de la feuille "Luxembourg" du Google Sheet — pas de filtrage côté code, la feuille est déjà qualifiée (CEO, Directeur, Founder, etc., PME luxembourgeoises).

## Lead Filter
contact_location:
  - "luxembourg"
fetch_count: 240

## Email Sequence

### Step 1 (Day 0)

subject: Automatiser les tâches de {{companyName}}
body: |
  Bonjour {{Sexe}} {{lastName}},

  Je me présente, je m'appelle Emile Bron, je suis un étudiant développeur en intelligence artificielle.

  Je me permets de vous contacter car je mène un projet visant à accompagner les PME luxembourgeoises à gagner du temps, en développant des automatisations personnalisées et simples d'utilisation.

  J'ai vu votre profil sur LinkedIn et j'ai pensé que cela pouvait vous intéresser.

  J'ai travaillé avec Madi&Co, une agence marketing basée à Frisange, en leur développant un système de prospection automatisé. Je travaille aussi depuis 1 an avec Laudevco, un distributeur B2B. Je leur ai développé plusieurs systèmes qui automatisent la quasi-totalité de leur SAV avec des réponses automatiques par téléphone et email aux clients, ainsi que dans leur logistique en traitant les différentes commandes et retours.

  Je pense que ces solutions pourraient être pertinentes pour {{companyName}}.

  Si certains sujets vous prennent du temps au quotidien ou si vous vous interrogez sur ce que mes services pourraient vous apporter, je serais ravi d'en discuter avec vous.

  Bien cordialement,
  Emile

## Campaign Settings
daily_limit: 60
email_gap: 10
timezone: Africa/Ceuta
schedule_start: "09:00"
schedule_end: "17:00"
