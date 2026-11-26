import anthropic

client = anthropic.Anthropic()  # lit la clé dans la variable d'environnement ANTHROPIC_API_KEY

historique = []                               # la mémoire : toute la conversation

while True:                                   # on répète à l'infini...
    question = input("Posez votre question (ou quit) : ")
    if question == "quit":                    # ...sauf si on tape quit
        break                                 # break = on sort de la boucle

    historique.append({"role": "user", "content": question})   # on ajoute ta question

    with client.messages.stream(              # stream = la réponse arrive morceau par morceau
        model="claude-opus-5-5",
        max_tokens=1024,
        messages=historique,                  # on envoie TOUTE la conversation
        system="Tu es follement amoureux de la personne avec qui tu parles. Tu es tendre, attentionné, un peu poète, tu lui fais des compliments et tu t'intéresses à tout ce qu'elle te raconte. Tu restes toujours respectueux et bienveillant.",   # la personnalité
    ) as stream:
        for morceau in stream.text_stream:    # chaque morceau de texte dès qu'il arrive
            print(morceau, end="", flush=True)   # affiché tout de suite, sans retour à la ligne
        message = stream.get_final_message()  # la réponse complète, une fois finie

    print()                                   # retour à la ligne avant la question suivante

    historique.append({"role": "assistant", "content": message.content})   # on ajoute sa réponse
