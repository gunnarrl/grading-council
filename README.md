Automatic grading of project transcripts using GPT, Claude, and Gemini.
First do their own evaluation, then see other models' evaluations and adjust their own.
Repeat until convergence.

For Dr. Palmer NSE 351.

Step 1: Create venv and install requirements

```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
```
    
Step 2: Create .env file

```bash
    cp .env.example .env
    fill in the keys
```

Step 3: Set class materials

```bash
    Upload all projects as PDFs to the main directory
    Update roster.csv with the following format:
    student_id,student_name,group_id,pdf_filename
```

Step 4: Summarise projects

```bash
    python summarize_projects.py
```
    
Step 5: Generate exam links

```bash
    python generate_exam_links.py
```
    
Step 6: Fetch transcripts

```bash
    python fetch_transcripts.py
```

Step 7: Grade each transcript

```bash
    python grading_script.py transcripts/[student_id]_transcript.txt [student_id]
```
