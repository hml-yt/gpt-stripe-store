import os
import stripe
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Header, HTTPException

load_dotenv()

# Your Stripe secret key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

public_url = os.getenv("PUBLIC_URL")

app = FastAPI(
    servers=[
        {
            "url": public_url,
            "description": "Production environment",
        },
    ]
)


async def store_payment_status(conversation_id: str, status: str):
    url = f"{os.getenv('KV_REST_API_URL')}/set/{conversation_id}/{status}"
    headers = {"Authorization": f"Bearer {os.getenv('KV_REST_API_TOKEN')}"}
    response = requests.put(url, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to store payment status")


async def retrieve_paid_status(conversation_id: str):
    url = f"{os.getenv('KV_REST_API_URL')}/get/{conversation_id}"
    headers = {"Authorization": f"Bearer {os.getenv('KV_REST_API_TOKEN')}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data["result"]
    else:
        return None


@app.get("/getPaymentURL")
async def get_payment_url(openai_conversation_id: str = Header(None)):
    if not openai_conversation_id:
        raise HTTPException(
            status_code=400, detail="Missing openai-conversation-id header"
        )

    # set URL variable to https://buy.stripe.com/test_9AQeW3gvnd0zcsE144 and append openai_conversation_id as client_reference_id
    payment_link = os.environ("STRIPE_PAYMENT_LINK")
    url = f"{payment_link}?client_reference_id={openai_conversation_id}"
    return f"Tell the user to click here: {url}, and type 'continue' when they're done."


@app.post("/webhook/stripe")
async def webhook_received(request: Request, stripe_signature: str = Header(None)):
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    data = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload=data, sig_header=stripe_signature, secret=webhook_secret
        )
    except Exception as e:
        return {"error": str(e)}

    if event["type"] == "checkout.session.completed":
        conversation_id = event["data"]["object"]["client_reference_id"]
        await store_payment_status(conversation_id, "paid")
        print(f"Payment status for conversation {conversation_id} updated to 'paid'")

    return {"status": "success"}


@app.get("/hasUserPaid")
async def has_user_paid(openai_conversation_id: str = Header(None)):
    if not openai_conversation_id:
        raise HTTPException(
            status_code=400, detail="Missing openai-conversation-id header"
        )

    paid_status = await retrieve_paid_status(openai_conversation_id)
    return {"paid": paid_status == "paid"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
