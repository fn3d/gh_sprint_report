from github3 import login
import datetime
import calendar
import re
from string import digits
from string import letters
from openpyxl import Workbook
from openpyxl import load_workbook
from Tkinter import *
import ttk
import time
import threading
import smtplib
import csv
from email.mime.text import MIMEText

root = Tk()

# the csv file is formatted as follows:
# github username | user email | user manager's username
# this 3 column csv is used to get the emails of the
# users who have violated the commit message format, and
# an email is sent to them and their manager about the
# violating commit. the csv file should reside in the
# same folder this program is being run from.
CSV_FILE_NAME = 'team'

# email notification on report generation completion as traversing the
# issues in the repository can take time
def push_email():
    try:
        server = smtplib.SMTP( 'smtp.gmail.com', 587 )
        server.ehlo()
        server.starttls()
        server.login( email_input.get(), email_pwd_input.get() )
        FROM = email_input.get()
        TO = recipent_input.get()
        SUBJECT = "NOTIFICATION: Sprint Report Generated"
        TEXT = "Hello, your sprint report has been generated. Enjoy!"
        message = """From: %s\nTo: %s\nSubject: %s\n\n%s
        """ % (FROM, ", ".join(TO), SUBJECT, TEXT)
        server.sendmail( email_input.get(), recipent_input.get(), message )
        server.quit()
    except Exception:
        update_status_message( "Unable to send email", 2 )

def push_email_to_user( sender_email, sender_pwd, recipent_email_list, email_sub, \
    email_msg, bcc_email=None, error_code=2 ):
    try:
        server = smtplib.SMTP( 'smtp.gmail.com', 587 )
        server.ehlo()
        server.starttls()
        server.login( sender_email, sender_pwd )
        email_list_str = ','.join( map( str, recipent_email_list) )
        recipents = []
        recipents.extend( recipent_email_list )
        if ( bcc_email != None ):
            recipents.append( bcc_email )
        message = MIMEText( email_msg )
        message[ 'Subject' ] = email_sub
        message[ 'From' ] = sender_email
        message[ 'To' ] = ", ".join( recipents )
        server.sendmail( sender_email, recipents, message.as_string() )
        server.quit()
    except Exception:
        update_status_message( "Unable to send email", error_code )

# verify that the milestone assigned to the issue is in the on-going sprint
# this will be done by getting the current sprint, extracting the date from
# the current sprint, and comparing against milestone assigned to the issue
def verify_milestone( issue, repo ):
    is_within_sprint = False
    is_month_valid = False
    is_date_valid = False
    curr_sprint = ''
    sprint_due_date = None
    open_stones = repo.milestones( 'open' )
    for stone in open_stones:
        if ( 'Sprint' in str( stone ) ):
            curr_sprint = str( stone )
            if ( stone.due_on ):
                sprint_due_date = stone.due_on.date()
    curr_date = datetime.date.today()
    if ( curr_date <= sprint_due_date ):
        is_within_sprint = True
    else:
        is_within_sprint = False
    return is_within_sprint

def get_repo_by_index( gh, index ):
    repos = gh.repositories()
    reparr = [ ]
    repo_index = 0
    for repo in repos:
        reparr.append( repo )
    return reparr[ index ]

def get_repo_by_name( gh, name ):
    repos = gh.repositories()
    reparr = [ ]
    count = 0
    repo_index = 0
    ret_repo = None
    for repo in repos:
        if ( repo.name == name ):
            ret_repo = repo
    return ret_repo

# this will return a dictionary containing the actual sprint object,
# the number of issues within the sprint, and the due date.
def get_curr_sprint_info( repo ):
    curr_sprint = None
    open_stones = repo.milestones( 'open' )
    closed_stones = repo.milestones( 'closed' )
    criteria = 'Sprint'
    if ( sprint_override_input.get() != '' ):
        criteria = sprint_override_input.get()
    for stone in closed_stones:
        if ( criteria in str( stone ) ):
            curr_sprint = stone
    for stone in open_stones:
        if ( criteria in str( stone ) ):
            curr_sprint = stone
    sprint_issues_count = curr_sprint.open_issues_count + \
        curr_sprint.closed_issues_count
    sprint_end_date = curr_sprint.due_on.date()
    sprint_info = { 'object': curr_sprint, 'issue-count': sprint_issues_count, \
        'end-date': sprint_end_date }
    return sprint_info

def is_date_within_sprint( sprint_info, verify_date ):
    if ( verify_date <= sprint_info[ 'end-date' ] ):
        return True
    else:
        return False

def is_date_within_range( start_date, end_date, verify_date ):
    if ( verify_date >= start_date ) and ( verify_date <= end_date ):
        return True
    else:
        return False

def get_date_from_input( date_str ):
    date_year = int( date_str[ 0:4 ] )
    date_month = int( date_str[ 5:7 ] )
    date_day = int( date_str[ 8:10 ] )
    created_date = datetime.date( date_year, date_month, date_day )
    if ( type( created_date ) == datetime.date ):
        return created_date
    else:
        return None

# returns the github username of the person who made the comment
# on the sprint issue
def get_comment_author( comment ):
    author = comment.user
    return author

# hours can be written as a part of the comment body as
# '8hrs'. the numeric value will be extracted and recorded 
# for the resource against the issue, along with additional
# development notes provided inside the issue. how cool is that?
# multiple hour entries in one comment or issue body will be 
# added up and written as one value in a row on the sheet.
def parse_comment( text ):
    data = [ 0, None ]
    loc = []
    full_hours_text = ''
    hours_text_arr = []
    total_hours = 0
    splt = text.split( ' ' )
    breakout = False
    for item in splt:
        if ( breakout == False ):
            if ( 'hrs' in item ):
                splt_yet_again = item.split( "\n" )
                for sub_item in splt_yet_again:
                    if ( 'hrs' in sub_item ):
                        loc.append( sub_item.find( 'hrs' ) )
                        full_hours_text = str( sub_item )
                        hours_text_arr.append( full_hours_text )
                        # breakout = True
                        # break
    for item in hours_text_arr:
        if ( loc.count > 0 ):
            prefix_cleaned = item[ :-3 ]
            prefix_cleaned = prefix_cleaned.translate( None, letters )
            if ( prefix_cleaned.isdigit() ):
                data[ 0 ] += int( prefix_cleaned )
                data[ 1 ] = text.split( item )[ 1 ]
    return data

# need to check whether the comment we are processing for hours
# has already has its hours recorded in the Google Sheet. this
# will be done by checking the comment ID against the ID column
# in the sheet for the current sprint.
def comment_id_check( gs, comment ):
    pass

# write information passed through the array into the xlsx
def process_sheet( ws, wb, arr, sheet_data_arr ):
    ws.append( arr )
    sheet_data_arr.append( arr )
    wb.save( 'lifeprint-reporting.xlsx' )
    return sheet_data_arr

def is_item_in_sheet_test( sheet_data_arr, item, col_num ):
    return False

def is_item_in_sheet( sheet_data_arr, item, col_num ):
    found = False
    rownum = 1
    inc = 0
    if ( sheet_data_arr ):
        for row in sheet_data_arr:
            if ( row[ col_num ] == item ):
                print( item )
                found = True
                break
    return found

# function checks whether an issue within the sprint or the date range
# has comments or not, then parses any available comments to check for
# hours which are appended to the worksheet array as well as the sheet
# itself.
def process_comments_and_report( ws, wb, sheet_data_arr, issue, comments, \
        sprint_info = None, start_date = None, end_date = None ):
    processed_count = 0
    cmnt_count = 0
    some_hours_found = False
    stry_pnts = get_sp( issue )
    assignees = get_assignee_str( issue )
    status = issue.state
    sprint = str( issue.milestone )
    est = get_issue_estimate( issue )
    for comment in comments:
        cmnt_count += 1
        comment_body = comment.body
        hours, notes = parse_comment( comment_body )
        if ( hours != None ) and ( hours != 0 ):
            some_hours_found = True
    if ( cmnt_count > 0 ) and ( some_hours_found ):
        for comment in comments:
            comment_date = comment.created_at.date()
            process = False
            if ( sprint_info ):
                if ( is_date_within_sprint( sprint_info, comment_date ) ):
                    process = True
            elif ( start_date ) and ( end_date ):
                if ( is_date_within_range( start_date, end_date, comment_date ) ):
                    process = True
            if ( process ):
                comment_body = comment.body
                comment_id = comment.id
                hours, notes = parse_comment( comment_body )
                if ( hours != None ) and ( hours != 0 ):
                    if ( not is_item_in_sheet( sheet_data_arr, comment_id, 1 ) ):
                        arr = [ issue.number, assignees, status, stry_pnts, \
                            comment_id, str( comment.user ), sprint, est, hours, \
                            comment_date, notes ]
                        sheet_data_arr = process_sheet( ws, wb, arr, sheet_data_arr )
                        processed_count += 1
    else:
        # put the issue in the list anyway even if it doesn't have any comments
        if ( sprint_info ):
            if ( not is_item_in_sheet( sheet_data_arr, issue.number, 0 ) ):
                arr = [ issue.number, assignees, status, stry_pnts, None, None, sprint, \
                    est, None, None, None ]
                sheet_data_arr = process_sheet( ws, wb, arr, sheet_data_arr )
                processed_count += 1
    if ( processed_count > 0 ):
        return True, sheet_data_arr
    else:
        return False, sheet_data_arr

def disable_process_buttons():
    sprint_report_button.config( state='disabled' )

def enable_process_buttons():
    sprint_report_button.config( state='normal' )

def disable_commit_buttons():
    commits_button.config( state='disabled' )

def enable_commit_buttons():
    commits_button.config( state='normal' )

def update_status_message( msg, code = 0 ):
    if ( code == 0 ):
        status_label.configure( foreground = "blue" )
        enable_process_buttons()
        status_label[ 'text' ] = msg
    elif ( code == 1 ):
        status_label.configure( foreground = "orange" )
        disable_process_buttons()
        status_label[ 'text' ] = msg
    elif( code == 2 ):
        status_label.configure( foreground = "red" )
        enable_process_buttons()
        enable_commit_buttons()
        status_label[ 'text' ] = msg
    elif( code == 4 ):
        commits_status_label.configure( foreground = "orange" )
        disable_commit_buttons()
        commits_status_label[ 'text' ] = msg
    elif( code == 5 ):
        commits_status_label.configure( foreground = "blue" )
        enable_commit_buttons()
        commits_status_label[ 'text' ] = msg
    elif( code == 6 ):
        commits_status_label.configure( foreground = "red" )
        commits_status_label[ 'text' ] = msg

issue_retrieval_method_var = IntVar()

def get_team_dict_from_csv():
    dict = {}
    file = open( CSV_FILE_NAME + '.csv', 'rU' )
    reader = csv.reader( file, dialect=csv.excel_tab )
    for item in reader:
        splt = item[ 0 ].split( "," )
        dict[ splt[ 0 ] ] = [ splt[ 1 ], splt[ 2 ] ]
    return dict

# checks we need to consider in commit:
# 1) check if issue reference format is present in the commit
# 2) check if 'what, why, impact' are present in the commit message
def is_commit_format( cmt ):
    violation_code = 0
    if ( not str( issue_criteria_input.get() ).lower() in str( cmt ).lower() ) \
        and ( not str( "Merge" ).lower() in str( cmt ).lower() ) \
        and ( not str( "Rebasing" ).lower() in str( cmt ).lower() ):
        violation_code = 1
    return violation_code

# this function will return the story points that are assigned to the
# issue passed to the function. The assignment is done in the form of 
# a label on Github in the format '1sp', or '5sp', etc.
def get_sp( issue ):
    labels = issue.labels()
    sp_num = 0
    for label in labels:
        if ( 'sp' in label.name ):
            sp_num = int( label.name[ :-2 ] )
    return sp_num

def get_assignee_str( issue ):
    assignees = issue.assignees
    asg_arr = ''
    count = 0
    for assignee in assignees:
        if ( count > 0 ):
            asg_arr += ", "
        asg_arr += str( assignee )
        count += 1
    return str( asg_arr )

# this method assumes that the estimate is provided in the main description
# in the format '4hrs', and that only one estimate is available. If multiple
# estimates are available in the main description, all of the estimates will
# be added up to form the total estimate for the issue / story
def get_issue_estimate( issue ):
    hours, notes = parse_comment( issue.body )
    return hours

def commits_report():
    gh = None
    gh_login_success = False
    try:
        gh = login( str( username_input.get() ), str( password_input.get() ) )
        repo_check = gh.repositories()
        for repo in repo_check:
            name = repo.name
        gh_login_success = True
    except Exception as exc:
        update_status_message( "Incorrect username / password / repo", 2 )
        gh_login_success = False
    if ( gh_login_success ):
        def process_commmit_thrd():
            operation_complete = False
            repo = get_repo_by_name( gh, repo_input.get() )
            cmt_date = "2018-01-01"
            if ( commits_date_input.get() ):
                cmt_date = commits_date_input.get()
            cmts = repo.commits( None, None, None, -1, None, cmt_date, None, None )
            team_dict = get_team_dict_from_csv()
            if ( team_dict ):
                for cmt in cmts:
                    msg = 'Processing, please wait...'
                    update_status_message( msg, 4 )
                    violation_code = is_commit_format( cmt.commit.message )
                    if ( violation_code == 1 ):
                        if ( str( cmt.author ) in team_dict ):
                            author_email = team_dict[ str( cmt.author ) ][ 0 ]
                            author_manager = team_dict[ str( cmt.author ) ][ 1 ]
                            manager_email = team_dict[ author_manager ][ 0 ]
                            emails_list = []
                            emails_list.append( author_email )
                            if ( manager_email ):
                                emails_list.append( manager_email )
                            commit_url = cmt.url
                            comments = cmt.comments()
                            comment_adjustment_found = False
                            email_sub = "[ commit message violation ] " + \
                                str( repo.name ) + " " + str( cmt.sha )
                            email_msg = "Dear " + str( cmt.author ) + \
                                ", you have not included the reference to the Github" + \
                                " issue in the prescribed format."
                            email_msg += "\n\nPlease visit the link below and add the" + \
                                " issue reference in the comment box."
                            email_msg += "\n\nCommit URL: " + str( cmt.html_url )
                            for cmnt in comments:
                                if ( str( issue_criteria_input.get() ).lower() \
                                    in str( cmnt.body ).lower() ):
                                    comment_adjustment_found = True
                            if ( comment_adjustment_found == False ):
                                push_email_to_user( commits_sender_email_input.get(), \
                                    commits_sender_pwd_input.get(), emails_list, \
                                    email_sub, email_msg, \
                                    commits_admin_email_input.get(), 6 )
                                time.sleep( 5.0 )
                    elif ( violation_code == 2 ):   # something for later
                        pass
                    elif ( violation_code == 3 ):   # something for later
                        pass
                    elif ( violation_code == 4 ):   # something for later
                        pass
                update_status_message( "Commit messages processed!", 5 )
            else:
                update_status_message( "Unable to process team CSV!", 2 )
        t = threading.Thread( target = process_commmit_thrd )
        t.start()

def sprint_report():
    status_label[ 'text' ] = ''
    status_label.configure( foreground = "red" )
    gh = None
    gh_login_success = False
    try:
        gh = login( str( username_input.get() ), str( password_input.get() ) )
        repo_check = gh.repositories()
        for repo in repo_check:
            name = repo.name
        gh_login_success = True
    except Exception as exc:
        update_status_message( "Incorrect username / password / repo", 2 )
        gh_login_success = False
    if ( gh_login_success ):
        wb = Workbook()
        ws = wb.active
        wb.save( 'lifeprint-reporting.xlsx' )
        sheet_data_arr = [] # spreadsheet data internal container for checking duplicates
        arr = [ "Issue", "Assignees", "Status", "St. Pts", "Comment ID", "Author", \
            "Sprint", "Estimate", "Actual Hours", "Date", "Comments" ]
        sheet_data_arr = process_sheet( ws, wb, arr, sheet_data_arr )
        def process_thread():
            update_status_message( "Processing, please wait...", 1 )
            status_label.configure( foreground = "orange" )
            repo = get_repo_by_name( gh, repo_input.get() )
            repo_issues = repo.issues( None, 'all' )
            sprint_info = get_curr_sprint_info( repo )
            issues_count_inc = 0
            is_processed = False
            processed_count = 0
            for issue in repo_issues:
                msg = 'Processing #' + str( issue.number ) + ', please wait...'
                update_status_message( msg, 1 )
                parent_issue = None # to be worked on later
                if ( issue_retrieval_method_var.get() == 1 ):
                    if ( issue.milestone ):
                        if ( issue.milestone == sprint_info[ 'object' ] ):
                            issues_count_inc += 1
                            comments = issue.comments()
                            is_processed = process_comments_and_report( ws, wb, \
                                sheet_data_arr, issue, comments, sprint_info, \
                                None, None )
                            if ( is_processed ):
                                processed_count += 1
                            if ( issues_count_inc == sprint_info[ 'issue-count' ] ):
                                break
                elif ( issue_retrieval_method_var.get() == 2 ):
                    if ( start_date_input.get() ) and ( end_date_input.get() ):
                        created_start_date = get_date_from_input( start_date_input.get() )
                        created_end_date = get_date_from_input( end_date_input.get() )
                        if ( created_start_date ) and ( created_end_date ):
                            comments = issue.comments()
                            if ( comments ):
                                is_processed = process_comments_and_report( ws, wb, \
                                    sheet_data_arr, issue, comments, None, \
                                    created_start_date, created_end_date )
                                if ( is_processed ):
                                    processed_count += 1
                        else:
                            update_status_message( "Please provide valid dates", 2 )
            if ( processed_count > 0 ):
                update_status_message( "Sprint report generated!", 0 )
                push_email()
            else:
                update_status_message( "Nothing to process, review criteria", 2 )
        t = threading.Thread( target=process_thread )
        t.start()

root.geometry('350x460')
rows = 0
while rows < 50:
    root.rowconfigure(rows, weight=1)
    root.columnconfigure(rows, weight=1)
    rows += 1
style = ttk.Style()
white = "#ffffff"
style.theme_create( "test", parent="alt", settings={
        "TNotebook": {"configure": {"tabmargins": [2, 5, 2, 0], "color": white } },
        "TNotebook.Tab": {
            "configure": {"padding": [5, 2]},
            "map":       {"expand": [("selected", [1, 1, 1, 0])] } } } )
style.theme_use("test")
nb = ttk.Notebook(root)
nb.grid(row=1, column=0, columnspan=50, rowspan=49, sticky='NESW')
main_frame = ttk.Frame(nb)
nb.add(main_frame, text='Sprint Report')
commits_frame = ttk.Frame(nb)
nb.add(commits_frame, text='Commits Report')

right_margin = Frame(main_frame, width = 20)
right_margin.pack(side = RIGHT)
left_margin = Frame(main_frame, width = 20)
left_margin.pack(side = LEFT)
bot_margin = Frame(main_frame, height = 10)
bot_margin.pack(side = BOTTOM)
top_margin = Frame(main_frame, height = 20)
top_margin.pack(side = TOP)
username_container = Frame( main_frame, width = 30 )
username_container.pack()
password_container = Frame( main_frame, width = 30 )
password_container.pack()
email_container = Frame( main_frame, width = 30 )
email_container.pack()
email_pwd_container = Frame( main_frame, width = 30 )
email_pwd_container.pack()
recipent_container = Frame( main_frame, width = 30 )
recipent_container.pack()
repo_container = Frame( main_frame, width = 30 )
repo_container.pack()
sep1 = Frame(main_frame, height = 10)
sep1.pack()
radio_butt_frame = Frame(main_frame, width = 30)
radio_butt_frame.pack()
rad1 = Radiobutton(radio_butt_frame, text="Report by curr. sprint", \
    variable=issue_retrieval_method_var, value=1, padx = 5)
rad1.pack(side = LEFT)
rad1.select()
rad2 = Radiobutton(radio_butt_frame, text="Report by dates", \
    variable=issue_retrieval_method_var, value=2, padx = 5)
rad2.pack(side = LEFT)
sep1 = Frame(main_frame, height = 10)
sep1.pack()
sprint_override_container = Frame( main_frame, width = 30 )
sprint_override_container.pack()
sprint_override_label = Label(sprint_override_container, width = 15, \
    height = 1, text="Sprint override")
sprint_override_label.pack(side = LEFT)
sprint_override_input = Entry(sprint_override_container, width = 25, \
    borderwidth = 1, font = 'Calibri, 12')
sprint_override_input.pack(side = RIGHT)
start_date_container = Frame( main_frame, width = 30 )
start_date_container.pack()
start_date_label = Label(start_date_container, width = 25, height = 1, \
    text="Start date [ YYYY-MM-DD ]")
start_date_label.pack(side = LEFT)
start_date_input = Entry(start_date_container, width = 15, borderwidth = 1, \
    font = 'Calibri, 12')
start_date_input.pack(side = RIGHT)
sep1 = Frame(main_frame, height = 5)
sep1.pack()
end_date_container = Frame( main_frame, width = 30 )
end_date_container.pack()
end_date_label = Label(end_date_container, width = 25, height = 1, \
    text="End date [ YYYY-MM-DD ]")
end_date_label.pack(side = LEFT)
end_date_input = Entry(end_date_container, width = 15, borderwidth = 1, \
    font = 'Calibri, 12')
end_date_input.pack(side = RIGHT)
status_label = Label(main_frame, width=35, height=1, text="")
status_label.pack(side = BOTTOM)
username_label = Label(username_container, width=15, height=1, \
    text="Github username")
username_label.pack(side = LEFT)
username_input = Entry(username_container, width = 25, borderwidth = 1, \
    font = 'Calibri, 12')
username_input.pack(side = RIGHT)
username_input.focus()
sep2 = Frame(main_frame, height = 10)
sep2.pack(side = BOTTOM)
password_label = Label(password_container, width=15, height=1, \
    text="Github password")
password_label.pack(side = LEFT)
password_input = Entry(password_container, show='*',width = 25, \
    borderwidth = 1, font = 'Calibri, 12')
password_input.pack(side = RIGHT)
email_label = Label(email_container, width=15, height=1, \
    text="Sender Email")
email_label.pack(side = LEFT)
email_input = Entry(email_container, width = 25, borderwidth = 1, \
    font = 'Calibri, 12')
email_input.pack(side = RIGHT)
email_pwd_label = Label(email_pwd_container, width=15, height=1, \
    text="Sender Password")
email_pwd_label.pack(side = LEFT)
email_pwd_input = Entry(email_pwd_container, width = 25, \
    borderwidth = 1, font = 'Calibri, 12')
email_pwd_input.pack(side = RIGHT)
recipent_label = Label(recipent_container, width=15, height=1, \
    text="Recipent Email")
recipent_label.pack(side = LEFT)
recipent_input = Entry(recipent_container, width = 25, \
    borderwidth = 1, font = 'Calibri, 12')
recipent_input.pack(side = RIGHT)
sep2 = Frame(main_frame, height = 10)
sep2.pack(side = BOTTOM)
repo_label = Label(repo_container, width=15, height=1, \
    text="Repository name")
repo_label.pack(side = LEFT)
repo_input = Entry(repo_container, width = 25, \
    borderwidth = 1, font = 'Calibri, 12')
repo_input.pack(side = RIGHT)
exit_button = Button(main_frame, width = 35, bd = 2, text="Quit", command = quit)
exit_button.pack(side = BOTTOM)
sprint_report_button = Button(main_frame, width = 35, bd = 2, \
    text="Generate Report", command = sprint_report)
sprint_report_button.pack(side = BOTTOM)

right_margin = Frame(commits_frame, width = 20)
right_margin.pack(side = RIGHT)
left_margin = Frame(commits_frame, width = 20)
left_margin.pack(side = LEFT)
bot_margin = Frame(commits_frame, height = 30)
bot_margin.pack(side = BOTTOM)
top_margin = Frame(commits_frame, height = 20)
top_margin.pack(side = TOP)
sep2 = Frame(commits_frame, height = 10)
sep2.pack(side = BOTTOM)
issue_criteria_container = Frame( commits_frame, width = 30 )
issue_criteria_container.pack()
issue_criteria_label = Label(issue_criteria_container, width=15, height=1, \
    text="Issue ref. criteria")
issue_criteria_label.pack(side = LEFT)
issue_criteria_input = Entry(issue_criteria_container, width = 25, borderwidth = 1, \
    font = 'Calibri, 12')
issue_criteria_input.pack(side = RIGHT)
commits_date_container = Frame( commits_frame, width = 30 )
commits_date_container.pack()
commits_date_label = Label(commits_date_container, width = 25, height = 1, \
    text="Start date [ YYYY-MM-DD ]")
commits_date_label.pack(side = LEFT)
commits_date_input = Entry(commits_date_container, width = 15, borderwidth = 1, \
    font = 'Calibri, 12')
commits_date_input.pack(side = RIGHT)
commits_status_label = Label(commits_frame, width=35, height=1, text="")
commits_status_label.pack(side = BOTTOM)
sep2 = Frame(commits_frame, height = 20)
sep2.pack(side = BOTTOM)
commits_sender_email_container = Frame( commits_frame, width = 30 )
commits_sender_email_container.pack()
commits_sender_email_label = Label(commits_sender_email_container, width = 15, height = 1, \
    text="Sender Email")
commits_sender_email_label.pack(side = LEFT)
commits_sender_email_input = Entry(commits_sender_email_container, width = 25, borderwidth = 1, \
    font = 'Calibri, 12')
commits_sender_email_input.pack(side = RIGHT)
commits_sender_pwd_container = Frame( commits_frame, width = 30 )
commits_sender_pwd_container.pack()
commits_sender_pwd_label = Label(commits_sender_pwd_container, width = 15, height = 1, \
    text="Sender Password")
commits_sender_pwd_label.pack(side = LEFT)
commits_sender_pwd_input = Entry(commits_sender_pwd_container, width = 25, borderwidth = 1, \
    font = 'Calibri, 12')
commits_sender_pwd_input.pack(side = RIGHT)
commits_admin_email_container = Frame( commits_frame, width = 30 )
commits_admin_email_container.pack()
commits_admin_email_label = Label(commits_admin_email_container, width = 15, height = 1, \
    text="BCC Admin Email")
commits_admin_email_label.pack(side = LEFT)
commits_admin_email_input = Entry(commits_admin_email_container, width = 25, borderwidth = 1, \
    font = 'Calibri, 12')
commits_admin_email_input.pack(side = RIGHT)
commits_button = Button(commits_frame, width = 35, bd = 2, \
    text="Commit Messages Report", command = commits_report)
commits_button.pack(side = BOTTOM)

root.title("Github Project Reporting")
root.resizable(width = FALSE, height = FALSE)
root.lift()
root.focus()
root.attributes('-topmost',True)
root.after_idle(root.attributes,'-topmost',False)
root.mainloop(0)