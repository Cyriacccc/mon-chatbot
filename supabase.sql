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

-- Autorise la clé secrète (rôle service_role) à lire, ajouter et modifier les lignes.
grant select, insert, update on public.chatbot_reglages to service_role;


-- ---------------------------------------------------------------------
-- Les conversations : une ligne par conversation, tout son contenu en JSON.
create table if not exists public.chatbot_conversations (
  id      text primary key,
  donnees jsonb not null,
  date    timestamptz not null default now()
);
alter table public.chatbot_conversations enable row level security;
grant select, insert, update, delete on public.chatbot_conversations to service_role;


-- ---------------------------------------------------------------------
-- Les documents ajoutés depuis la page (pour le RAG) : on garde seulement leur texte.
create table if not exists public.chatbot_documents (
  nom   text primary key,
  texte text not null,
  date  timestamptz not null default now()
);
alter table public.chatbot_documents enable row level security;
grant select, insert, update, delete on public.chatbot_documents to service_role;
