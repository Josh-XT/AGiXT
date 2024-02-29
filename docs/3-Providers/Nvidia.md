# Getting Started with the Nvidia provider

**NOTE: THIS PROVIDER ONLY SUPPORTS TEXT BASED MODELS**

To begin using this provider, follow these steps:

1. Visit Nvidia's NGC catalog at [catalog.ngc.nvidia.com](https://catalog.ngc.nvidia.com/).

2. Choose the model you want to use. For this example, we'll use Mistral's 7B Instruct model. You can find it at:
   [Mistral 7b Instruct Model](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/ai-foundation/models/mistral-7b-instruct/overview)

3. Once you've selected the model, navigate to the API section. Under the "Shell" language tab, switch to the "Python" language tab. You will find an attribute labeled `invoke_url`. This is the `API_URI` you will need to place this in your `AGENT` settings.

4. To proceed, you must log in to the Nvidia developer account and retrieve your API Key from the model page by hitting generate api key in that api tab. Place this API Key in the `AGENT` settings.

Now you are ready to utilize the selected model.
