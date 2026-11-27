-- Table où le chatbot range son compteur de dépenses et son budget.
-- Une ligne par réglage : cle = "total" ou "budget", valeur = le contenu en JSON.
create table if not exists public.chatbot_reglages (
  cle    text primary key,
  valeur jsonb not null
);

-- Sécurité : on active la protection RLS sans aucune règle.
-- Personne ne peut lire ou modifier la table avec la clé publique ;
-- seul le chatbot, avec la clé secrète (gardée dans les Secrets Streamlit), y a accès.
alter table public.chatbot_reglages enable row level security;
