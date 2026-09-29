import asyncio
import aiohttp
import os
OUTPUT_DIR = "images/original_images"

async def download_image(session: aiohttp.ClientSession, seed: int, semaphore: asyncio.Semaphore):
    url = f"https://picsum.photos/seed/{seed}/800/600"
    filepath = os.path.join(OUTPUT_DIR, f"image_{seed}.jpg")

    async with semaphore:
        async with session.get(url) as response:
            response.raise_for_status()
            content = await response.read()
            
    with open(filepath, "wb") as f:
        f.write(content)
    print(f"Downloaded {filepath}")

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    semaphore = asyncio.Semaphore(10)
    async with aiohttp.ClientSession() as session:
        tasks = [download_image(session, seed, semaphore) for seed in range(1, 101)]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())