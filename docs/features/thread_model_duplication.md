# Feature: Thread Model Duplication

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

I see that we have models (app/models.py) for both `ThreadSeries` and `ThreadForm`, but there seems to be a lot of duplication between them. Additionally, the forms in our UI seem to only use ThreadSeries. Please determine where, if anywhere, ThreadForm is used. Assuming my understanding is correct that we're really only relying on ThreadSeries now, please remove ThreadForm and update ThreadSeries to include any ThreadForm values that it doesn't already. Update any code that was using ThreadForm to now use ThreadSeries.
