## Descrizione dell'API

L'API offre un singolo endpoint che consente di:

1. Ricevere in input un video codificato in Base64.
2. Estrarre un set di frame dal video (secondo criteri specificati dall'utente o di default).
3. Ridimensionare i frame a una risoluzione desiderata.
4. Analizzare in sequenza ciascun frame, generando una descrizione qualitativa e coerente con i frame precedenti.
5. Infine, generare una descrizione finale che riassume il contenuto visivo del video nel suo complesso.

L'API si basa su FastAPI, dunque espone un endpoint HTTP `POST` che riceve in input un payload JSON, elabora i dati, e restituisce un oggetto JSON con le descrizioni generate.

## Endpoint Disponibile

### `POST /analyze_video`

#### Descrizione

Questo endpoint riceve un video in Base64, estrae un certo numero di frame (specificato dall'utente tramite `num_frames` o `frame_rate`), ridimensiona i frame, li analizza uno per uno fornendo al modello la sequenza delle descrizioni precedenti per garantire coerenza, e infine produce una descrizione finale del video.

#### Parametri Input (Request Body)

Il corpo della richiesta deve essere un JSON che corrisponde al modello `VideoRequest` definito nel codice:

- `video_base64` (**stringa**, obbligatorio): Il video codificato in Base64.  
  Il video deve essere fornito come stringa Base64 di un file MP4. Esempio: `"AAAAGGZ0eXBpc29..."`.

- `num_frames` (**intero**, opzionale):  
  Numero di frame da estrarre in modo uniforme dal video.  
  Se fornito, il video verrà suddiviso idealmente in segmenti uguali e verrà estratto un frame per ciascun segmento.

- `frame_rate` (**intero**, opzionale):  
  Frequenza di frame da estrarre in base al frame rate del video. Ad esempio, se si specifica `frame_rate=1`, verrà estratto indicativamente un frame al secondo.  
  Se `num_frames` è definito, viene ignorato `frame_rate`.

- `width` (**intero**, obbligatorio):  
  Larghezza in pixel a cui ridimensionare ogni frame estratto.

- `height` (**intero**, obbligatorio):  
  Altezza in pixel a cui ridimensionare ogni frame estratto.

Note:  
- Se né `num_frames` né `frame_rate` vengono forniti, verranno estratti di default 5 frame equidistanti.
- È obbligatorio fornire `width` e `height`.

#### Output (Response Body)

La risposta è un JSON con la seguente struttura:

- `frame_descriptions`: lista di stringhe, ciascuna rappresenta la descrizione qualitativa di un frame, nell'ordine in cui i frame sono stati analizzati.
- `final_description`: stringa contenente la descrizione finale dell'intero video.

Esempio di output:

```json
{
  "frame_descriptions": [
    "Questo frame mostra una scena luminosa, con presenza di oggetti chiari...",
    "Nel frame successivo si nota un cambio di luminosità e alcuni dettagli..."
  ],
  "final_description": "Il video presenta una successione di scene con variazioni di luce..."
}
```

#### Codici di Risposta

- `200 OK`: La richiesta è andata a buon fine, e la descrizione del video è stata generata.
- `422 Unprocessable Entity`: Se il body non rispetta il modello previsto (ad esempio, mancanza di `video_base64` o parametri non validi).
- `500 Internal Server Error`: In caso di errori durante l'elaborazione (ad esempio, formati video non supportati, errori di parsing del modello).

## Esempi di Utilizzo

### Esempio 1: Estrazione di un numero fisso di frame

Richiesta:

- Si fornisce un video in base64 (ipotetico, non riportato integralmente per brevità).
- Si vogliono estrarre 5 frame.
- Si ridimensionano i frame a 224x224 pixel.

```bash
curl -X POST "http://localhost:8000/analyze_video" \
     -H "Content-Type: application/json" \
     -d '{
       "video_base64": "AAAAGGZ0eXBpc29...",
       "num_frames": 5,
       "width": 224,
       "height": 224
     }'
```

Risposta (esempio):

```json
{
  "frame_descriptions": [
    "Il primo frame mostra un paesaggio urbano con colori tenui e una leggera foschia.",
    "Nel secondo frame, la scena rimane urbana ma si notano dettagli leggermente diversi nella disposizione degli edifici.",
    "Il terzo frame presenta un cambio di prospettiva, con un punto di vista leggermente più alto.",
    "Il quarto frame è più luminoso, con un leggero bagliore del sole sui tetti.",
    "Il quinto frame mantiene lo scenario cittadino, ma l'illuminazione sembra più uniforme."
  ],
  "final_description": "Nel complesso, il video mostra una serie di panorami urbani con variazioni di luce e prospettiva, mantenendo un'atmosfera coerente e armoniosa."
}
```

### Esempio 2: Estrazione in base a frame_rate

Richiesta:

- Nessun `num_frames` fornito.
- `frame_rate=1` significa che si tenterà di estrarre all'incirca un frame per ogni secondo di video.
- Ridimensionamento a 128x128 pixel.

```bash
curl -X POST "http://localhost:8000/analyze_video" \
     -H "Content-Type: application/json" \
     -d '{
       "video_base64": "AAAAGGZ0eXBpc29...",
       "frame_rate": 1,
       "width": 128,
       "height": 128
     }'
```

Risposta (esempio):

```json
{
  "frame_descriptions": [
    "Il primo frame mostra un interno di una stanza con illuminazione artificiale.",
    "Il secondo frame presenta un leggero spostamento della camera, con più dettagli visibili su un tavolo.",
    "Il terzo frame evidenzia uno scaffale sullo sfondo, con oggetti di diversi colori.",
    "Il quarto frame sembra più vicino a una finestra, con una luce più naturale.",
    "Il quinto frame torna a una vista più ampia, mostrando pareti chiare e un'atmosfera tranquilla."
  ],
  "final_description": "Il video nel suo insieme mostra una stanza interna con elementi di arredo e oggetti su piani di lavoro. La luce varia tra artificiale e naturale, suggerendo un ambiente quotidiano, stabile e privo di elementi di disturbo."
}
```

### Esempio 3: Mancanza di parametri frame

Se non si forniscono né `num_frames` né `frame_rate`, l'endpoint estrarrà 5 frame di default:

```bash
curl -X POST "http://localhost:8000/analyze_video" \
     -H "Content-Type: application/json" \
     -d '{
       "video_base64": "AAAAGGZ0eXBpc29...",
       "width": 256,
       "height": 256
     }'
```

La risposta avrà comunque lo stesso formato, con 5 frame descritti.
