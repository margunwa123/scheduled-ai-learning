1. 3 parts of qdrant point:
   1. vectors
   2. id
   3. payload
   4. And yes, definetely, payload & payload key can differ between collections
2. We cannot mix vectors from 2 embedding, because embeddings have different configurations, different vectors altogether from one another. At collection creation, the collection name and the collection number of dimensions are fixed.
3.  Embeding is stored exactly one time per point BUT, the pointer to the embeddnig can be duplicated between layers.
    1.  Dropping down, means that it goes a layer down, and continue to search neighbors that have better match. Dropping down means there's no better alternative at the top layer
4.  When you normalize a vector, its length goes down to 1, which makes magnitude dissapears from the picture, and it turns all 3 methods to direct functions of the angle between the vectors.
5.  Qdrant planner does help a lot on the kind of search algo that'll be the fastest to use. IF we have a filter on, and it turns out there's a lot of items, then it can choose to use the HNSW & trim method. BUT if it's small enough, it can use brute force on the specific points, so that it'll be much faster.
6.  Nope, it just means the data that matches the filter AND high enough to return an acceptable match threshold.
7.  Actually, I just think we just lose some time here when adding? (it'll read all 1M points). Other than that, not sure.
8.  it's like the diff between plain SELECT and SELECT with GROUP BY. Query points groups will query like normal, but later group down based on one similar payload key, so that if the "similar payload key" happens to appear multiple times on the list, it'll be merged to the highest rank between the points. We will need the 2nd one IF we plan to have a functionality that will have to filter through payload keys a lot.
9. client.count(collection_name) for counting number of points... but not sure about how to count payload field or what does that actually means.
10. must_not is to filter out; filter not is contraint?
11. It's because the last sentences gets truncated in this system, and even if it goes in, some part of the tokens are sacrificed which make searchig much less accurate. Truncation isn't whole story for short plots, because the short plots fit the token size limit that the embedding model accepts
12. Basically, I was not considering that duplicate chunks on the same film, can make the ranking not exactly accurate, because each chunks have carry-over sentences, some non-exact chunk with different point id but same film id might appear higher in the ranking. We fix it by making the ranking judge per-film basis rather than point id basis in the chunking.
13. Hmmm actually not sure? Is there any acceptable threshold, or any research where we can say, MRR 60% BAD, MRR below 30% trash. Anything like that? 