# Building Chains Manually

## Create your Chain folder
Under chains folder create a folder with the name of your chain like:

`Generate Cat Jokes`

## Chain Step 1
In the `Generate Cat Jokes` folder, create a text file called `1-AGENTNAME-instruct.txt` replacing `AGENTNAME` with your agent name.

Content of the file:
```
Search online for 10 cat jokes
```

## Chain Step 2
In the `Generate Cat Jokes` folder, create a text file called `2-AGENTNAME-instruct.txt` replacing `AGENTNAME` with your agent name.

Content of the file:
```
Write 10 cat jokes to catjokes.txt
```

## Chain Step N
In the `Generate Cat Jokes` folder, create a text file called `N-AGENTNAME-instruct.txt` replacing `AGENTNAME` with your agent name and `N` with the step number.

## Run your chain
Run the following command to run your chain:

```
python3 Chain.py --chain "Generate Cat Jokes"
```