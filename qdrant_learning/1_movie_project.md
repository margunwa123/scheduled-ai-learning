# Project: “Describe a movie, find it”

You type a vague description (“a robot learns to love while cleaning an abandoned Earth”) and get back ranked films, then narrow with filters. Build it in one notebook, in stages. Each stage is a Qdrant feature you’ll use later in the benchmark.

1. Load and clean (pandas). Sample the rows, drop missing plots, and turn genre into a real list.
2. Embed once. Use intfloat/multilingual-e5-small (384 dimensions), the same model as your benchmark spec. It needs passage: on documents and query: on queries. Save the vectors to a .npy file so you never re-embed.
3. Create the collection and bulk-upsert. Use batches of a few hundred. Put title, year (an integer), genres (a list) and director in the payload, and keep the plot text out of the vector path.
4. Search. Run 5–10 descriptions you invent, including a few in Indonesian against the English plots. Whether that cross-lingual retrieval works is useful information for the benchmark.
5. Filters you haven’t used yet. Add a Range condition on year (1990–2005) and a list match on genres (MatchAny). Combine them with must/must_not. Create an integer index on year and a keyword index on genres.
6. Use facet on genres to see how many films fall in each bucket. Then work out which of your filters would be about 50% selective and which about 1%, using real counts instead of guesses.
7. Query by example. Pass an existing film’s point id as the query (“more like this one”) and add a negative example. This is Qdrant’s recommendation-style search.
8. Scroll and update. Page through results with scroll, then fix one film’s payload with set_payload without re-uploading its vector.